/*
Counts a page view for views decorated with `track_view_counter` and exposes
the count the server returns, so any element on the page can display it.

`new_base.html` requires this script and sets the body attributes whenever the
view's context carries `track_events`. Templates need nothing else; to show the
count, bind to the store from any Alpine root:

```
<span x-text="$store.viewCount.value"></span>
```

`value` stays `null` until the response arrives, and for good when the request
fails. Failures are logged to the console and never shown to the user.
*/

document.addEventListener('alpine:init', () => {
  Alpine.store('viewCount', {
    label: '',
    value: null,
    async init() {
      const { viewCountLabel, viewCountUrl } = document.body.dataset;
      this.label = viewCountLabel;
      try {
        const response = await fetch(viewCountUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: this.label }),
        });
        if (!response.ok) {
          console.error(`Could not count view for ${this.label}: HTTP ${response.status}`);
          return;
        }
        const data = await response.json();
        this.value = data.value;
      } catch (error) {
        console.error(`Could not count view for ${this.label}:`, error);
      }
    },
  });
});
