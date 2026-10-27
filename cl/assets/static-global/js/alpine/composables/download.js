/*
Downloads the file a link points to without leaving the page, in Alpine's
CSP-friendly build, which doesn't support inline JavaScript. `busy` is true
while the request runs; a non-2xx response sets `error` instead of
navigating away. A redirect, such as an expired session, sends the browser to
the redirect's target with its `next` parameter pointed back at the current
page, so signing in returns here. Without JavaScript the link still downloads
natively.

Usage:

```
{% load component_tags %}
{% require_script "js/alpine/composables/download.js" %}
```

Example:
```
<div x-data="download">
  <a href="/docket/1/download/" x-on:click.prevent="start" x-bind:aria-busy="busy">
    Export CSV
  </a>
  <span x-show="error" x-cloak role="alert">There was a problem. Try again later.</span>
</div>
```
*/

document.addEventListener('alpine:init', () => {
  Alpine.data('download', () => ({
    busy: false,
    error: false,
    async start(event) {
      if (this.busy) return;
      const url = event.currentTarget.href;
      this.busy = true;
      this.error = false;
      try {
        const response = await fetch(url);
        if (response.redirected) {
          const target = new URL(response.url);
          target.searchParams.set('next', location.pathname + location.search);
          window.location.href = target.href;
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const filename = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/)?.[1];
        const link = document.createElement('a');
        link.href = URL.createObjectURL(await response.blob());
        link.download = filename ?? '';
        document.body.appendChild(link);
        link.click();
        link.remove();
        // Revoking before the download starts cancels it in some browsers.
        setTimeout(() => URL.revokeObjectURL(link.href));
      } catch (error) {
        console.error(`Could not download ${url}:`, error);
        this.error = true;
      } finally {
        this.busy = false;
      }
    },
  }));
});
