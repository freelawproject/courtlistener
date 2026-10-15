/*
Counts a page view and exposes the returned count as the `viewCount` store.
Loaded by `new_base.html` for views decorated with `track_view_counter`;
templates never require it. Usage and caveats: FRONTEND.md, "View counting".
*/

document.addEventListener('alpine:init', () => {
  Alpine.store('viewCount', {
    value: null,
    get loaded() {
      return this.value !== null;
    },
    async init() {
      const { viewCountLabel: label, viewCountUrl } = document.body.dataset;
      try {
        const response = await fetch(viewCountUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label }),
        });
        if (!response.ok) {
          console.error(`Could not count view for ${label}: HTTP ${response.status}`);
          return;
        }
        const data = await response.json();
        this.value = data.value;
      } catch (error) {
        console.error(`Could not count view for ${label}:`, error);
      }
    },
  });
});
