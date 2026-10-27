/*
Downloads the file a link points to without leaving the page, in Alpine's
CSP-friendly build, which doesn't support inline JavaScript. `busy` is true
while the request runs. A failed request sets `errorMessage` instead of
navigating away, picked from the root element's `data-error-message-<status>`
attributes with `data-error-message-default` as the fallback; without a
default, a failure shows nothing. A redirect whose target carries a `next`
parameter is taken as a sign-in redirect: the browser goes there with `next`
pointed back at the current page, so signing in returns here. Without
JavaScript the link still downloads natively.

Usage:

```
{% load component_tags %}
{% require_script "js/alpine/composables/download.js" %}
```

Example:
```
<div
  x-data="download"
  data-error-message-429="Too many downloads. Try again in an hour."
  data-error-message-default="There was a problem. Try again later."
>
  <a href="/docket/1/download/" x-on:click.prevent="start" x-bind:aria-busy="busy">
    Export CSV
  </a>
  <span x-show="errorMessage" x-text="errorMessage" x-cloak role="alert"></span>
</div>
```
*/

document.addEventListener('alpine:init', () => {
  Alpine.data('download', () => ({
    busy: false,
    errorMessage: '',
    async start(event) {
      if (this.busy) return;
      const url = event.currentTarget.href;
      this.busy = true;
      this.errorMessage = '';
      let status = 0;
      try {
        const response = await fetch(url);
        const target = response.redirected ? new URL(response.url) : null;
        if (target?.searchParams.has('next')) {
          target.searchParams.set('next', location.pathname + location.search);
          window.location.href = target.href;
          return;
        }
        status = response.status;
        if (!response.ok) throw new Error(`HTTP ${status}`);
        const filename = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1];
        this.saveBlob(await response.blob(), filename ?? '');
      } catch (error) {
        console.error(`Could not download ${url}:`, error);
        this.errorMessage = this.errorMessageFor(status);
      } finally {
        this.busy = false;
      }
    },
    /** Saves a blob through a temporary link, as a click on a download link would. */
    saveBlob(blob, filename) {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Revoking before the download starts cancels it in some browsers.
      setTimeout(() => URL.revokeObjectURL(link.href));
    },
    /** The error message the root element declares for a status, or its default one. */
    errorMessageFor(status) {
      return (
        this.$root.getAttribute(`data-error-message-${status}`) ||
        this.$root.getAttribute('data-error-message-default') ||
        ''
      );
    },
  }));
});
