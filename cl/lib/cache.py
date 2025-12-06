import time
from hashlib import md5

from django.conf import settings
from django.core.cache import caches
from django.middleware.cache import CacheMiddleware

from django.utils.cache import _i18n_cache_key_suffix  # type: ignore[attr-defined] # isort: skip
from django.utils.cache import (
    cc_delim_re,
    get_cache_key,
    get_max_age,
    has_vary_header,
    learn_cache_key,
    patch_response_headers,
)
from django.utils.http import parse_http_date_safe
from django_s3_express_cache import S3ExpressCacheBackend


def _generate_cache_key_s3_compatible(request, method, headerlist, key_prefix):
    """
    Generate a cache key compatible with S3ExpressCacheBackend.

    Django's default `_generate_cache_key` places the key_prefix near the
    end of the key, preventing the prefix from being used as a time-based
    directory prefix required by S3ExpressCacheBackend.

    Additionally, Django's default keys may include forward slashes ('/').
    In S3, slashes create nested folders, which is undesirable for our
    implementation.

    This helper ensures:
      • key_prefix appears at the start of the key (enables time-based prefixing)
      • all '/' characters are replaced with '.' to prevent nested folders
      • URL and Vary-based hashes follow afterward for uniqueness

    Key format:
        "<prefix>:views.decorators.cache.cache_page.<method>.<urlhash>.<varyhash>"
    """
    ctx = md5(usedforsecurity=False)
    for header in headerlist:
        value = request.META.get(header)
        if value:
            ctx.update(value.encode())

    url_hash = md5(
        request.build_absolute_uri().encode("ascii"), usedforsecurity=False
    )
    raw_key = f"{key_prefix}:views.decorators.cache.cache_page.{method}.{url_hash.hexdigest()}.{ctx.hexdigest()}"

    return _i18n_cache_key_suffix(request, raw_key).replace("/", ".")


def _generate_cache_header_key_s3_compatible(key_prefix, request):
    """
    Generate the S3-compatible header cache key.

    Stores the list of headers that affect caching (Vary headers) in a key
    format compatible with S3ExpressCacheBackend:

      • key_prefix is at the beginning to allow time-based prefixing
      • '/' characters are replaced with '.' to prevent nested folder creation
      • the key is otherwise deterministic based on the URL
    """
    url_hash = md5(
        request.build_absolute_uri().encode("ascii"), usedforsecurity=False
    )
    raw_key = f"{key_prefix}:views.decorators.cache.cache_header.{url_hash.hexdigest()}"
    return _i18n_cache_key_suffix(request, raw_key).replace("/", ".")


def get_cache_key_s3_compatible(
    request, key_prefix=None, method="GET", cache=None
):
    """
    Mirrors Django's `get_cache_key` but generates a key compatible with
    S3ExpressCacheBackend by:

      • placing key_prefix at the beginning of the key
      • replacing '/' with '.' to avoid creating nested S3 folders

    If there isn't a headerlist stored, return None, indicating that the page
    needs to be rebuilt.
    """
    key_prefix = key_prefix or settings.CACHE_MIDDLEWARE_KEY_PREFIX
    cache = cache or caches[settings.CACHE_MIDDLEWARE_ALIAS]

    header_key = _generate_cache_header_key_s3_compatible(key_prefix, request)
    headerlist = cache.get(header_key)
    if headerlist is None:
        return None

    return _generate_cache_key_s3_compatible(
        request, method, headerlist, key_prefix
    )


def learn_cache_key_s3_compatible(
    request, response, cache_timeout=None, key_prefix=None, cache=None
):
    """
    Store the list of headers from the response's Vary header and generate
    an S3-compatible cache key.

    This mirrors Django's `learn_cache_key` but ensures keys are compatible
    with S3ExpressCacheBackend:

      • key_prefix appears at the start of the key (for time-based prefixing)
      • '/' characters are replaced with '.' to prevent nested folder.
      • all other behavior (Vary handling, sorting, i18n suffix) remains
        the same as Django
    """
    key_prefix = key_prefix or settings.CACHE_MIDDLEWARE_KEY_PREFIX
    cache_timeout = cache_timeout or settings.CACHE_MIDDLEWARE_SECONDS
    cache = cache or caches[settings.CACHE_MIDDLEWARE_ALIAS]

    cache_key = _generate_cache_header_key_s3_compatible(key_prefix, request)
    headerlist = []
    if response.has_header("Vary"):
        is_accept_language_redundant = settings.USE_I18N
        for header in cc_delim_re.split(response.headers["Vary"]):
            header = header.upper().replace("-", "_")
            if header != "ACCEPT_LANGUAGE" or not is_accept_language_redundant:
                headerlist.append("HTTP_" + header)
        headerlist.sort()

    # if there is no Vary header, we still need a cache key
    # for the request.build_absolute_uri()
    cache.set(cache_key, headerlist, cache_timeout)
    return _generate_cache_key_s3_compatible(
        request, request.method, headerlist, key_prefix
    )


class CacheMiddlewareS3Compatible(CacheMiddleware):
    """
    Drop-in replacement for Django's CacheMiddleware that produces
    cache keys compatible with S3ExpressCacheBackend.

    This middleware automatically switches to S3-compatible key generation
    when using `S3ExpressCacheBackend`.

    For non-S3 backends, the middleware falls back to Django’s standard
    cache key generation.
    """

    def _use_s3_backend(self) -> bool:
        return isinstance(self.cache, S3ExpressCacheBackend)

    @property
    def _get_cache_key_func(self):
        return (
            get_cache_key_s3_compatible
            if self._use_s3_backend()
            else get_cache_key
        )

    @property
    def _learn_cache_key_func(self):
        return (
            learn_cache_key_s3_compatible
            if self._use_s3_backend()
            else learn_cache_key
        )

    def process_request(self, request):
        if request.method not in ("GET", "HEAD"):
            request._cache_update_cache = False
            return None  # Don't bother checking the cache.

        # Use the appropriate cache key generator based on backend:
        #   • S3 backend -> use S3-compatible helpers.
        #   • default backend -> use Django's standard helpers.
        key_func = self._get_cache_key_func
        cache_key = key_func(request, self.key_prefix, "GET", cache=self.cache)
        if cache_key is None:
            # No cache information available, need to rebuild.
            request._cache_update_cache = True
            return None

        response = self.cache.get(cache_key)
        # if it wasn't found and we are looking for a HEAD, try looking just for that
        if response is None and request.method == "HEAD":
            cache_key = key_func(
                request, self.key_prefix, "HEAD", cache=self.cache
            )
            response = self.cache.get(cache_key)

        if response is None:
            # No cache information available, need to rebuild.
            request._cache_update_cache = True
            return None

        # Derive the age estimation of the cached response.
        max_age_seconds = get_max_age(response)
        expires_timestamp = parse_http_date_safe(response.get("Expires"))

        if max_age_seconds is not None and expires_timestamp is not None:
            now_timestamp = int(time.time())
            remaining_seconds = expires_timestamp - now_timestamp
            # Use Age: 0 if local clock got turned back.
            response["Age"] = max(0, max_age_seconds - remaining_seconds)

        # hit, return cached response
        request._cache_update_cache = False
        return response

    def process_response(self, request, response):
        """Store the response in cache when appropriate."""
        if not self._should_update_cache(request, response):
            # We don't need to update the cache, just return.
            return response

        if response.streaming or response.status_code not in (200, 304):
            return response

        # Don't cache responses that set a user-specific (and maybe security
        # sensitive) cookie in response to a cookie-less request.
        if (
            not request.COOKIES
            and response.cookies
            and has_vary_header(response, "Cookie")
        ):
            return response

        # Don't cache a response with 'Cache-Control: private'
        if "private" in response.get("Cache-Control", ()):
            return response

        # Page timeout takes precedence over the "max-age" and the default
        # cache timeout.
        timeout = (
            self.page_timeout or get_max_age(response) or self.cache_timeout
        )
        if timeout == 0:
            return response

        patch_response_headers(response, timeout)

        # Store or learn the cache key using the correct backend function.
        learn_func = self._learn_cache_key_func
        cache_key = learn_func(
            request, response, timeout, self.key_prefix, cache=self.cache
        )
        if timeout and response.status_code == 200:
            if hasattr(response, "render") and callable(response.render):
                response.add_post_render_callback(
                    lambda r: self.cache.set(cache_key, r, timeout)
                )
            else:
                self.cache.set(cache_key, response, timeout)
        return response
