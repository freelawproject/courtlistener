"""Read-only census of accounts that share an email address.

CourtListener never enforced email uniqueness, so some people hold several
accounts under one address. Before those accounts can be merged (see
``merge_users`` and its issue), somebody has to know how many groups exist,
what data they hold, and which ones a machine must not touch. This module
answers that. It only reads: the database queries are SELECTs and the Redis
commands are ZCARD, ZSCAN and ZRANGE.

The vocabulary used throughout:

- A *group* is every account whose ``LOWER(TRIM(email))`` matches.
- The *primary* is the account the merge would keep. Highest ``last_login``
  wins, accounts that never logged in sort last, and ties go to the lowest pk.
- A *secondary* is any other account in the group.
- A *blocker* is a condition that removes a group from the automatic merge
  and sends it to a human.

The census output is a concentrated PII artifact: addresses paired with
usernames, API volumes, membership and login recency. Never commit it and
never leave it anywhere public.
"""

import csv
import logging
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import batched, product
from typing import IO, Any

import pghistory.models
from django.contrib.auth.models import User
from django.db.models import Count, ForeignObjectRel, QuerySet, Value
from django.db.models.functions import Lower, Trim
from django.utils.timezone import now
from oauth2_provider.models import AccessToken, RefreshToken
from oauth2_provider.settings import oauth2_settings
from redis import Redis

from cl.api.models import APIThrottle, Webhook
from cl.api.utils import get_logging_prefix, get_webhook_logging_prefix
from cl.donate.models import NeonMembership
from cl.favorites.models import UserTag
from cl.lib.redis_utils import get_redis_interface
from cl.recap.models import EmailProcessingQueue
from cl.users.models import UserProfile

logger = logging.getLogger(__name__)

# Recent API usage on a secondary means the account we would delete is in
# active programmatic use. Six months, per the census issue.
RECENT_API_WINDOW_DAYS = 180

# Credential ownership (throttles, API token, OAuth grants) is decided by
# lifetime API usage. Lifetime will over-block old accounts, so the summary
# also reports how many groups each of these shorter windows would block, to
# let that parameter be chosen on data. None means lifetime.
CREDENTIAL_WINDOWS_DAYS: tuple[int | None, ...] = (None, 365, 180)

# A primary that joined this recently while an older secondary holds data is
# the signature of a planted account. See the census issue.
RECENT_JOIN_DAYS = 30

# How far back to look for @recap.email traffic when deciding whether an
# address is in use.
RECAP_EMAIL_WINDOW_DAYS = 365

# Rows every account has (or that carry no user data) do not make a
# secondary "non-empty" for the date_joined guard. Every user gets an API
# token at creation, and thousands of accounts hold grandfathered throttle
# rows without ever having used the API.
DATA_FREE_RELATIONS = frozenset(
    {
        "users.userprofile.user",
        "authtoken.token.user",
        "api.apithrottle.user",
    }
)

# Blocker classes. The values are the strings that appear in the CSV and the
# summary, so keep them stable once the triage runbook starts using them.
BLOCKER_PRIVILEGED = "privileged"
BLOCKER_INACTIVE = "inactive"
BLOCKER_STUB = "stub"
BLOCKER_UNCONFIRMED = "unconfirmed"
BLOCKER_MEMBERSHIPS = "multiple_memberships"
BLOCKER_WEBHOOKS = "webhooks_on_multiple"
BLOCKER_RECENT_API = "recent_api_on_secondary"
BLOCKER_API_HISTORY = "api_history_on_multiple"
BLOCKER_OAUTH = "oauth_on_multiple"
BLOCKER_RECAP_EMAIL = "recap_email_on_multiple"
BLOCKER_PUBLISHED_TAGS = "published_tags_on_secondary"
BLOCKER_PUBLIC_PRAYERS = "public_prayers_on_secondary"
BLOCKER_RECENT_PRIMARY = "recent_primary_older_secondary"
BLOCKER_CLASSES = (
    BLOCKER_PRIVILEGED,
    BLOCKER_INACTIVE,
    BLOCKER_STUB,
    BLOCKER_UNCONFIRMED,
    BLOCKER_MEMBERSHIPS,
    BLOCKER_WEBHOOKS,
    BLOCKER_RECENT_API,
    BLOCKER_API_HISTORY,
    BLOCKER_OAUTH,
    BLOCKER_RECAP_EMAIL,
    BLOCKER_PUBLISHED_TAGS,
    BLOCKER_PUBLIC_PRAYERS,
    BLOCKER_RECENT_PRIMARY,
)

# Postgres and Python disagree on case folding for some non-ASCII input, and
# the LOWER(email) index on auth_user uses the Postgres implementation. Every
# email comparison here therefore goes through this expression, never
# str.lower().
EMAIL_KEY = Lower(Trim("email"))

# Sized so that IN (...) lists stay comfortable for the planner.
PK_CHUNK_SIZE = 1000


def window_label(days: int | None) -> str:
    """Name a credential-ownership window for the summary and the CSV.

    :param days: The window length, or None for lifetime.
    :return: A short, stable label.
    """
    return "lifetime" if days is None else f"{days}d"


def _today() -> date:
    """Today's date, for the ``ApiUsage.as_of`` default."""
    return now().date()


@dataclass
class ApiUsage:
    """Redis API counters, loaded once and joined against accounts in Python.

    Token-authenticated API traffic never updates ``last_login``, so an
    account used purely as an integration looks untouched in ``auth_user``.
    These counters are the only record of that use.

    :ivar lifetime: Total v3 + v4 requests ever made, by user pk.
    :ivar last_request: The most recent day with any request, by user pk,
        for the ``history_days`` most recent days only.
    :ivar webhooks: Successful webhook deliveries ever, by user pk.
    :ivar history_days: How many days of per-day keys were scanned.
    :ivar as_of: The day the census ran; windows count back from here.
    """

    lifetime: dict[int, int] = field(default_factory=dict)
    last_request: dict[int, date] = field(default_factory=dict)
    webhooks: dict[int, int] = field(default_factory=dict)
    history_days: int = 0
    as_of: date = field(default_factory=_today)

    def active_within(self, pk: int, days: int | None) -> bool:
        """Did this account make any API request within the window?

        :param pk: The user pk.
        :param days: The window length, or None for lifetime. A finite window
            longer than ``history_days`` is silently truncated to the history
            that was loaded; callers pick ``history_days`` to cover the
            longest window they ask about.
        :return: True if the account made a request in the window.
        """
        if days is None:
            return self.lifetime.get(pk, 0) > 0
        last = self.last_request.get(pk)
        return last is not None and last >= self.as_of - timedelta(days=days)


def _member_pk(member: str) -> int | None:
    """Convert a sorted-set member to a user pk.

    The request logger writes ``AnonymousUser`` for unauthenticated traffic,
    and old data holds the string ``None``. Neither is an account.

    :param member: The raw member string from Redis.
    :return: The pk, or None for the members that are not accounts.
    """
    try:
        return int(member)
    except ValueError:
        return None


def _load_totals(r: Redis, key: str, into: Counter[int]) -> None:
    """Add every member's score from a sorted set into a counter.

    Uses ZSCAN rather than a single ZRANGE: the lifetime sets can hold a
    million members, and a whole-set ZRANGE would block Redis while it
    serializes them.

    :param r: The Redis connection.
    :param key: The sorted-set key.
    :param into: The counter to add scores into, keyed by user pk.
    :return: None
    """
    for member, score in r.zscan_iter(key, count=1000):
        if (pk := _member_pk(member)) is not None:
            into[pk] += int(score)


def load_api_usage(
    history_days: int,
    r: Redis | None = None,
    as_of: date | None = None,
) -> ApiUsage:
    """Load the API and webhook counters from Redis into memory.

    Three lifetime sets are read with ZSCAN, then one ZRANGE per per-day key
    for the last ``history_days`` days of both API versions. Per-day detail is
    collapsed into "most recent day with a request" as it arrives; only
    membership in a window matters downstream.

    :param history_days: How many days of per-day keys to read. Must cover the
        longest finite window in ``CREDENTIAL_WINDOWS_DAYS``.
    :param r: The STATS Redis connection; resolved from settings if omitted.
    :param as_of: The day to count back from; today if omitted.
    :return: The loaded counters.
    """
    r = r or get_redis_interface("STATS")
    as_of = as_of or now().date()
    usage = ApiUsage(history_days=history_days, as_of=as_of)

    prefixes = [get_logging_prefix(version) for version in ("v3", "v4")]
    lifetime_keys = [f"{prefix}.user.counts" for prefix in prefixes]
    webhook_key = f"{get_webhook_logging_prefix()}.user.counts"

    # One round trip tells us how big the in-memory dicts are about to be.
    pipe = r.pipeline()
    for key in [*lifetime_keys, webhook_key]:
        pipe.zcard(key)
    for key, cardinality in zip(
        [*lifetime_keys, webhook_key], pipe.execute(), strict=True
    ):
        logger.info("Redis key %s has %s members", key, cardinality)

    lifetime: Counter[int] = Counter()
    for key in lifetime_keys:
        _load_totals(r, key, lifetime)
    usage.lifetime = dict(lifetime)

    webhooks: Counter[int] = Counter()
    _load_totals(r, webhook_key, webhooks)
    usage.webhooks = dict(webhooks)

    # Oldest day first, so that the last write for a pk is its newest day.
    days = [
        as_of - timedelta(days=offset)
        for offset in range(history_days - 1, -1, -1)
    ]
    day_keys = list(product(days, prefixes))
    pipe = r.pipeline()
    for day, prefix in day_keys:
        pipe.zrange(f"{prefix}.user.d:{day.isoformat()}.counts", 0, -1)
    for (day, _prefix), members in zip(day_keys, pipe.execute(), strict=True):
        for member in members:
            if (pk := _member_pk(member)) is not None:
                usage.last_request[pk] = day
    return usage


def duplicate_email_keys(email: str | None = None) -> QuerySet:
    """The normalized addresses that more than one account shares.

    Blank addresses are excluded even though none exist today: one future
    admin-created account without an email would otherwise collapse every
    emailless account into a single fake group.

    :param email: Restrict to this one address, compared through the same
        database expression as the grouping. Used to investigate a report.
    :return: A values queryset of ``email_key`` strings.
    """
    qs = (
        User.objects.exclude(email="")
        .annotate(email_key=EMAIL_KEY)
        .exclude(email_key="")
        .values("email_key")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
    )
    if email:
        qs = qs.filter(email_key=Lower(Trim(Value(email))))
    return qs.values("email_key")


def duplicate_users(email: str | None = None) -> QuerySet:
    """Every account that belongs to a duplicate group, grouped and ordered.

    :param email: Restrict to this one address; see ``duplicate_email_keys``.
    :return: Users annotated with ``email_key`` and ``username_key`` (both
        folded by the database), ordered by group then pk.
    """
    return (
        User.objects.annotate(
            email_key=EMAIL_KEY, username_key=Lower("username")
        )
        .filter(email_key__in=duplicate_email_keys(email))
        .order_by("email_key", "pk")
    )


def choose_primary(accounts: Sequence["AccountFacts"]) -> "AccountFacts":
    """Pick the account a merge would keep.

    Highest ``last_login`` wins, accounts that never logged in sort last, and
    ties go to the lowest pk. Only ``django.contrib.auth.login()`` writes
    ``last_login``, so API-only use does not count here; the API-usage
    blockers cover that case instead.

    :param accounts: The accounts in one group.
    :return: The primary.
    """
    return min(
        accounts,
        key=lambda a: (
            a.user.last_login is None,
            -a.user.last_login.timestamp() if a.user.last_login else 0,
            a.user.pk,
        ),
    )


def counted_relations() -> list[ForeignObjectRel]:
    """The reverse relations to ``User`` whose rows the census counts.

    Introspected rather than listed, so a new foreign key to ``User`` shows
    up in the CSV without anyone remembering to add it. Many-to-many
    relations (auth groups and permissions, waffle flags) are handled by
    name. pghistory models are skipped: the event tables are audit trail
    rather than user data (the merge purges them separately), and the
    aggregate ``pghistory_events`` view is not a table at all.

    :return: The relations, in ``User._meta`` order.
    """
    return [
        rel
        for rel in User._meta.related_objects
        if not rel.many_to_many
        and not issubclass(
            rel.related_model,
            (pghistory.models.Event, pghistory.models.Events),
        )
    ]


def relation_label(rel: ForeignObjectRel) -> str:
    """Name a relation the way the CSV header and ``DATA_FREE_RELATIONS`` do.

    :param rel: The reverse relation.
    :return: ``app.model.field`` in lower case, e.g. ``alerts.alert.user``.
    """
    return f"{rel.related_model._meta.label_lower}.{rel.field.name}"


def count_by_user(
    qs: QuerySet, pks: Iterable[int], user_field: str
) -> Counter[int]:
    """Count rows per user for the given pks, in chunked GROUP BY queries.

    :param qs: The queryset to count within. Any filters it carries apply.
    :param pks: The user pks to count for.
    :param user_field: The name of the FK to ``User`` on the model.
    :return: Row counts keyed by user pk. Users with no rows are absent.
    """
    counts: Counter[int] = Counter()
    for chunk in batched(pks, PK_CHUNK_SIZE):
        rows = (
            qs.filter(**{f"{user_field}__in": chunk})
            .values(user_field)
            .annotate(n=Count("pk"))
        )
        for row in rows:
            counts[row[user_field]] += row["n"]
    return counts


def recap_emails_in_use(days: int = RECAP_EMAIL_WINDOW_DAYS) -> set[str]:
    """Every @recap.email address that received a notification recently.

    ``EmailProcessingQueue.destination_emails`` is filled straight from the
    SES receipt's recipients. One pass over the window is cheaper than a
    per-group JSON containment query, which would scan the table every time
    without a GIN index. Addresses are normalized in Python because they
    live inside JSON; the generated ``recap_email`` values they are compared
    with are lower case already.

    :param days: How far back to look.
    :return: The addresses, lower-cased and stripped.
    """
    cutoff = now() - timedelta(days=days)
    addresses: set[str] = set()
    destinations = (
        EmailProcessingQueue.objects.filter(date_created__gte=cutoff)
        .values_list("destination_emails", flat=True)
        .iterator(chunk_size=5000)
    )
    for recipients in destinations:
        for address in recipients or []:
            addresses.add(address.strip().lower())
    return addresses


def username_email_collisions() -> list[tuple[User, User]]:
    """Accounts whose username is another account's email address.

    Runs across the whole table, not just duplicate groups: this is the
    audit list the email-login work needs, because such a username is
    ambiguous the moment people can sign in with an address. An account
    whose username is its *own* email is not a collision.

    :return: ``(account, owner)`` pairs, where ``account.username`` equals
        ``owner.email`` case-insensitively.
    """
    email_keys = (
        User.objects.exclude(email="")
        .annotate(email_key=EMAIL_KEY)
        .values("email_key")
    )
    colliders: list[tuple[int, str]] = list(
        User.objects.annotate(username_key=Lower("username"))
        .filter(username_key__in=email_keys)
        .order_by("pk")
        .values_list("pk", "username_key")
    )
    if not colliders:
        return []
    owners_by_key: defaultdict[str, list[int]] = defaultdict(list)
    for chunk in batched(colliders, PK_CHUNK_SIZE):
        owners = (
            User.objects.annotate(email_key=EMAIL_KEY)
            .filter(email_key__in=[key for _pk, key in chunk])
            .order_by("pk")
            .values_list("email_key", "pk")
        )
        for email_key, owner_pk in owners:
            owners_by_key[email_key].append(owner_pk)
    pairs = [
        (pk, owner_pk)
        for pk, key in colliders
        for owner_pk in owners_by_key[key]
        if owner_pk != pk
    ]
    users = User.objects.in_bulk({pk for pair in pairs for pk in pair})
    return [(users[pk], users[owner_pk]) for pk, owner_pk in pairs]


@dataclass
class AccountFacts:
    """Everything the census learned about one account.

    :ivar user: The account.
    :ivar profile: Its profile, or None for the rare account without one.
    :ivar email_key: ``LOWER(TRIM(email))`` as the database computed it.
    :ivar username_key: ``LOWER(username)`` as the database computed it.
    :ivar n_groups: Auth group memberships.
    :ivar n_permissions: Explicit auth permissions.
    :ivar has_membership: Whether a ``NeonMembership`` row exists.
    :ivar n_webhooks: ``Webhook`` rows.
    :ivar n_throttles: ``APIThrottle`` rows.
    :ivar n_published_tags: ``UserTag`` rows with ``published`` set.
    :ivar n_live_oauth: Unexpired access tokens plus unrevoked refresh tokens.
    :ivar recap_email_in_use: Whether the profile's @recap.email address
        received a notification in the window.
    :ivar username_is_email_of: Pks of accounts whose email address equals
        this account's username.
    :ivar relation_counts: Rows per counted relation, keyed by
        ``relation_label``.
    """

    user: User
    profile: UserProfile | None
    email_key: str
    username_key: str
    n_groups: int = 0
    n_permissions: int = 0
    has_membership: bool = False
    n_webhooks: int = 0
    n_throttles: int = 0
    n_published_tags: int = 0
    n_live_oauth: int = 0
    recap_email_in_use: bool = False
    username_is_email_of: list[int] = field(default_factory=list)
    relation_counts: dict[str, int] = field(default_factory=dict)

    def holds_data(self, usage: ApiUsage) -> bool:
        """Does this account hold anything a merge would have to carry over?

        :param usage: The loaded API counters.
        :return: True if any data-bearing relation has rows or the account
            has ever used the API.
        """
        if usage.lifetime.get(self.user.pk, 0) > 0:
            return True
        return any(
            n
            for label, n in self.relation_counts.items()
            if label not in DATA_FREE_RELATIONS
        )

    @property
    def is_privileged(self) -> bool:
        """Staff, superuser, in an auth group, or holding a permission."""
        return bool(
            self.user.is_staff
            or self.user.is_superuser
            or self.n_groups
            or self.n_permissions
        )


@dataclass
class DuplicateGroup:
    """One email address and the accounts that share it.

    :ivar email_key: The normalized address the group was built on.
    :ivar accounts: The accounts, ordered by pk.
    :ivar primary: The account a merge would keep.
    :ivar blockers: Blocker classes present, in ``BLOCKER_CLASSES`` order.
    :ivar active_accounts_by_window: How many accounts used the API within
        each credential window, keyed by ``window_label``.
    """

    email_key: str
    accounts: list[AccountFacts]
    primary: AccountFacts
    blockers: list[str] = field(default_factory=list)
    active_accounts_by_window: dict[str, int] = field(default_factory=dict)

    @property
    def secondaries(self) -> list[AccountFacts]:
        """The accounts a merge would delete."""
        return [a for a in self.accounts if a is not self.primary]

    @property
    def neon_account_ids(self) -> list[str]:
        """Distinct non-blank Neon account IDs in the group, for the Neon
        worklist."""
        ids = {
            a.profile.neon_account_id
            for a in self.accounts
            if a.profile and a.profile.neon_account_id
        }
        return sorted(ids)


def find_blockers(group: DuplicateGroup, usage: ApiUsage) -> list[str]:
    """Decide which blocker classes apply to a group.

    Two of these are security controls rather than caution, and must not be
    relaxed to speed up a backfill. Anyone can register a second account on
    a known address; a confirmed planted account could sign in, become the
    primary, and inherit the victim's alerts, tokens and @recap.email
    address. ``unconfirmed`` blocks that, and ``recent_primary_older_secondary``
    catches it even if the confirmation check is somehow satisfied.

    :param group: The group, with account facts filled in.
    :param usage: The loaded API counters.
    :return: Blocker classes present, in ``BLOCKER_CLASSES`` order.
    """
    primary = group.primary
    secondaries = group.secondaries
    found: set[str] = set()

    for account in group.accounts:
        if account.is_privileged:
            found.add(BLOCKER_PRIVILEGED)
        if not account.user.is_active:
            found.add(BLOCKER_INACTIVE)
        # An account without a profile cannot be confirmed either.
        if account.profile is None or not account.profile.email_confirmed:
            found.add(BLOCKER_UNCONFIRMED)
        if account.profile and account.profile.stub_account:
            found.add(BLOCKER_STUB)

    if sum(a.has_membership for a in group.accounts) > 1:
        found.add(BLOCKER_MEMBERSHIPS)
    if sum(a.n_webhooks > 0 for a in group.accounts) > 1:
        found.add(BLOCKER_WEBHOOKS)
    if sum(a.n_live_oauth > 0 for a in group.accounts) > 1:
        found.add(BLOCKER_OAUTH)
    if sum(a.recap_email_in_use for a in group.accounts) > 1:
        found.add(BLOCKER_RECAP_EMAIL)
    if group.active_accounts_by_window[window_label(None)] > 1:
        found.add(BLOCKER_API_HISTORY)

    for account in secondaries:
        if usage.active_within(account.user.pk, RECENT_API_WINDOW_DAYS):
            found.add(BLOCKER_RECENT_API)
        if account.n_published_tags:
            found.add(BLOCKER_PUBLISHED_TAGS)
        if account.profile and account.profile.prayers_public:
            found.add(BLOCKER_PUBLIC_PRAYERS)

    recent_join_cutoff = now() - timedelta(days=RECENT_JOIN_DAYS)
    if primary.user.date_joined >= recent_join_cutoff and any(
        a.user.date_joined < primary.user.date_joined and a.holds_data(usage)
        for a in secondaries
    ):
        found.add(BLOCKER_RECENT_PRIMARY)

    return [b for b in BLOCKER_CLASSES if b in found]


def build_account_facts(users: QuerySet) -> list[AccountFacts]:
    """Run the bulk lookups for every account in every group.

    Each fact is one chunked query across all pks rather than a query per
    account, so the census stays at a fixed number of statements however
    many groups exist.

    :param users: The queryset from ``duplicate_users``. Its ordering and
        its ``email_key`` / ``username_key`` annotations are relied on.
    :return: Facts in queryset order. ``relation_counts`` is populated for
        every counted relation, with zero for relations without rows.
    """
    keyed: list[tuple[int, str, str]] = list(
        users.values_list("pk", "email_key", "username_key")
    )
    pks = [pk for pk, _email_key, _username_key in keyed]
    if not pks:
        return []
    user_by_pk = User.objects.in_bulk(pks)
    profile_by_pk: dict[int, UserProfile] = {}
    for chunk in batched(pks, PK_CHUNK_SIZE):
        for profile in UserProfile.objects.filter(user_id__in=chunk):
            profile_by_pk[profile.user_id] = profile
    facts = [
        AccountFacts(
            user=user_by_pk[pk],
            profile=profile_by_pk.get(pk),
            email_key=email_key,
            username_key=username_key,
        )
        for pk, email_key, username_key in keyed
    ]

    groups = count_by_user(User.groups.through.objects.all(), pks, "user")
    permissions = count_by_user(
        User.user_permissions.through.objects.all(), pks, "user"
    )
    memberships = count_by_user(NeonMembership.objects.all(), pks, "user")
    webhooks = count_by_user(Webhook.objects.all(), pks, "user")
    throttles = count_by_user(APIThrottle.objects.all(), pks, "user")
    published_tags = count_by_user(
        UserTag.objects.filter(published=True), pks, "user"
    )
    # A live grant is an unexpired access token or an unrevoked, unexpired
    # refresh token. Refresh tokens carry no expiry column; the toolkit
    # derives it from ``created`` and the configured lifetime, so do the
    # same. With access tokens at an hour and refresh tokens at thirty days,
    # a client unused for a month has nothing here and re-authorizes on its
    # next use.
    live_refresh = RefreshToken.objects.filter(revoked__isnull=True)
    if refresh_lifetime := oauth2_settings.REFRESH_TOKEN_EXPIRE_SECONDS:
        live_refresh = live_refresh.filter(
            created__gt=now() - timedelta(seconds=refresh_lifetime)
        )
    live_oauth = count_by_user(
        AccessToken.objects.filter(expires__gt=now()), pks, "user"
    ) + count_by_user(live_refresh, pks, "user")
    in_use = recap_emails_in_use()

    # Which accounts own an email address equal to one of these usernames?
    # Both sides are folded by the database: ``username_key`` was annotated
    # by ``duplicate_users`` and ``email_key`` is computed here.
    owners_by_username: defaultdict[str, list[int]] = defaultdict(list)
    for chunk in batched(facts, PK_CHUNK_SIZE):
        owners = (
            User.objects.annotate(email_key=EMAIL_KEY)
            .filter(email_key__in=[a.username_key for a in chunk])
            .values_list("email_key", "pk")
        )
        for email_key, owner_pk in owners:
            owners_by_username[email_key].append(owner_pk)

    relation_counts = {
        relation_label(rel): count_by_user(
            rel.related_model._base_manager.all(), pks, rel.field.name
        )
        for rel in counted_relations()
    }

    for account in facts:
        pk = account.user.pk
        account.n_groups = groups[pk]
        account.n_permissions = permissions[pk]
        account.has_membership = memberships[pk] > 0
        account.n_webhooks = webhooks[pk]
        account.n_throttles = throttles[pk]
        account.n_published_tags = published_tags[pk]
        account.n_live_oauth = live_oauth[pk]
        recap_email = account.profile.recap_email if account.profile else ""
        account.recap_email_in_use = (
            bool(recap_email) and recap_email in in_use
        )
        account.username_is_email_of = [
            owner
            for owner in owners_by_username[account.username_key]
            if owner != pk
        ]
        account.relation_counts = {
            label: counts[pk] for label, counts in relation_counts.items()
        }
    return facts


def build_groups(
    facts: Iterable[AccountFacts], usage: ApiUsage
) -> list[DuplicateGroup]:
    """Assemble account facts into groups and evaluate each one.

    :param facts: Per-account facts from ``build_account_facts``, ordered by
        ``email_key`` then pk.
    :param usage: The loaded API counters.
    :return: The groups, in email order.
    """
    by_key: defaultdict[str, list[AccountFacts]] = defaultdict(list)
    for account in facts:
        by_key[account.email_key].append(account)

    groups: list[DuplicateGroup] = []
    for email_key, members in by_key.items():
        group = DuplicateGroup(
            email_key=email_key,
            accounts=members,
            primary=choose_primary(members),
        )
        group.active_accounts_by_window = {
            window_label(days): sum(
                usage.active_within(a.user.pk, days) for a in members
            )
            for days in CREDENTIAL_WINDOWS_DAYS
        }
        group.blockers = find_blockers(group, usage)
        groups.append(group)
    return groups


@dataclass
class CensusReport:
    """The complete result of one census run.

    :ivar groups: Every duplicate group, in email order.
    :ivar collisions: Whole-table username-vs-email collisions, as
        ``(account, owner)`` pairs. Empty when the run was restricted to one
        address.
    :ivar usage: The API counters the run used.
    """

    groups: list[DuplicateGroup]
    collisions: list[tuple[User, User]]
    usage: ApiUsage

    @property
    def blocker_counts(self) -> Counter[str]:
        """Groups per blocker class, with every class present."""
        counts: Counter[str] = Counter({b: 0 for b in BLOCKER_CLASSES})
        for group in self.groups:
            counts.update(group.blockers)
        return counts

    @property
    def mergeable_groups(self) -> int:
        """Groups with no blocker at all."""
        return sum(not g.blockers for g in self.groups)

    def credential_window_blockers(self) -> dict[str, int]:
        """Groups where more than one account used the API, per window.

        This is the dial the merge issue leaves open: lifetime is the current
        rule, and these numbers say what a shorter window would cost.

        :return: Blocked group counts keyed by ``window_label``.
        """
        return {
            window_label(days): sum(
                g.active_accounts_by_window[window_label(days)] > 1
                for g in self.groups
            )
            for days in CREDENTIAL_WINDOWS_DAYS
        }

    def summary_lines(self) -> list[str]:
        """The human-readable summary printed at the end of a run.

        :return: Lines of text, without trailing newlines.
        """
        n_accounts = sum(len(g.accounts) for g in self.groups)
        lines = [
            f"Duplicate groups: {len(self.groups)}",
            f"Accounts in those groups: {n_accounts}",
            f"Groups with no blocker: {self.mergeable_groups}",
            "Groups per blocker class:",
        ]
        lines.extend(
            f"  {blocker}: {n}" for blocker, n in self.blocker_counts.items()
        )
        lines.append(
            "Groups blocked by API usage on more than one account, per "
            "credential-ownership window:"
        )
        lines.extend(
            f"  {label}: {n}"
            for label, n in self.credential_window_blockers().items()
        )
        lines.append(
            "Accounts whose username is another account's email address: "
            f"{len(self.collisions)}"
        )
        return lines


def run_census(
    email: str | None = None,
    history_days: int | None = None,
    r: Redis | None = None,
) -> CensusReport:
    """Run the whole census without writing anything.

    :param email: Restrict to the group for this address. The whole-table
        username scan is skipped in that case, since it is unrelated to any
        one group.
    :param history_days: Days of per-day API keys to read. Defaults to the
        longest finite window in ``CREDENTIAL_WINDOWS_DAYS``.
    :param r: The STATS Redis connection; resolved from settings if omitted.
    :return: The report.
    """
    if history_days is None:
        history_days = max(d for d in CREDENTIAL_WINDOWS_DAYS if d)
    usage = load_api_usage(history_days, r=r)
    facts = build_account_facts(duplicate_users(email))
    groups = build_groups(facts, usage)
    collisions = [] if email else username_email_collisions()
    return CensusReport(groups=groups, collisions=collisions, usage=usage)


def _iso(value: datetime | date | None) -> str:
    """Format a timestamp for the CSV, blank for None."""
    return value.isoformat() if value else ""


def account_csv_columns() -> list[str]:
    """The header of the per-account CSV.

    Fixed columns first, then one ``n:<relation>`` column per counted
    relation, so the header follows the models without manual upkeep.

    :return: Column names in order.
    """
    fixed = [
        "group_email",
        "group_size",
        "group_blockers",
        "group_neon_account_ids",
        "is_primary",
        "user_id",
        "username",
        "email",
        "date_joined",
        "last_login",
        "is_active",
        "is_staff",
        "is_superuser",
        "n_auth_groups",
        "n_auth_permissions",
        "email_confirmed",
        "stub_account",
        "neon_account_id",
        "has_membership",
        "n_webhooks",
        "n_throttles",
        "api_lifetime_requests",
        "api_last_request",
        *(
            f"api_active_{window_label(days)}"
            for days in CREDENTIAL_WINDOWS_DAYS
            if days
        ),
        "webhook_lifetime_events",
        "n_live_oauth_grants",
        "recap_email",
        "recap_email_in_use",
        "n_published_tags",
        "prayers_public",
        "username_is_email_of",
    ]
    return fixed + [f"n:{relation_label(rel)}" for rel in counted_relations()]


def account_rows(report: CensusReport) -> Iterator[dict[str, Any]]:
    """One CSV row per account, in group order.

    :param report: The census report.
    :return: Rows keyed by ``account_csv_columns``.
    """
    usage = report.usage
    for group in report.groups:
        for account in group.accounts:
            user, profile = account.user, account.profile
            row: dict[str, Any] = {
                "group_email": group.email_key,
                "group_size": len(group.accounts),
                "group_blockers": ";".join(group.blockers),
                "group_neon_account_ids": ";".join(group.neon_account_ids),
                "is_primary": account is group.primary,
                "user_id": user.pk,
                "username": user.username,
                "email": user.email,
                "date_joined": _iso(user.date_joined),
                "last_login": _iso(user.last_login),
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "n_auth_groups": account.n_groups,
                "n_auth_permissions": account.n_permissions,
                "email_confirmed": profile.email_confirmed if profile else "",
                "stub_account": profile.stub_account if profile else "",
                "neon_account_id": profile.neon_account_id if profile else "",
                "has_membership": account.has_membership,
                "n_webhooks": account.n_webhooks,
                "n_throttles": account.n_throttles,
                "api_lifetime_requests": usage.lifetime.get(user.pk, 0),
                "api_last_request": _iso(usage.last_request.get(user.pk)),
                "webhook_lifetime_events": usage.webhooks.get(user.pk, 0),
                "n_live_oauth_grants": account.n_live_oauth,
                "recap_email": profile.recap_email if profile else "",
                "recap_email_in_use": account.recap_email_in_use,
                "n_published_tags": account.n_published_tags,
                "prayers_public": profile.prayers_public if profile else "",
                "username_is_email_of": ";".join(
                    str(pk) for pk in account.username_is_email_of
                ),
            }
            for days in CREDENTIAL_WINDOWS_DAYS:
                if days:
                    row[f"api_active_{window_label(days)}"] = (
                        usage.active_within(user.pk, days)
                    )
            for label, n in account.relation_counts.items():
                row[f"n:{label}"] = n
            yield row


def write_account_csv(report: CensusReport, out: IO[str]) -> None:
    """Write the per-account CSV.

    :param report: The census report.
    :param out: An open text stream.
    :return: None
    """
    writer = csv.DictWriter(out, fieldnames=account_csv_columns())
    writer.writeheader()
    writer.writerows(account_rows(report))


COLLISION_CSV_COLUMNS = [
    "user_id",
    "username",
    "email",
    "owner_user_id",
    "owner_username",
    "owner_email",
]


def write_collision_csv(report: CensusReport, out: IO[str]) -> None:
    """Write the whole-table username-vs-email collision list.

    :param report: The census report.
    :param out: An open text stream.
    :return: None
    """
    writer = csv.DictWriter(out, fieldnames=COLLISION_CSV_COLUMNS)
    writer.writeheader()
    for account, owner in report.collisions:
        writer.writerow(
            {
                "user_id": account.pk,
                "username": account.username,
                "email": account.email,
                "owner_user_id": owner.pk,
                "owner_username": owner.username,
                "owner_email": owner.email,
            }
        )
