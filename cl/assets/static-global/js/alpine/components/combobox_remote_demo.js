document.addEventListener('alpine:init', () => {
  /**
   * Consumer of the Component Library's remote combobox demo: answers
   * `combobox-search` with the page the components view returns.
   */
  Alpine.data('comboboxRemoteDemo', () => ({
    async answer({ detail }) {
      const { searchUrl, errorMessage } = this.$root.dataset;
      const params = new URLSearchParams({ combobox: 'search', q: detail.query, page: detail.page });
      try {
        const response = await fetch(`${searchUrl}?${params}`, { signal: detail.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const page = await response.json();
        detail.respond(page.results, { hasMore: page.has_more });
      } catch (error) {
        if (error.name !== 'AbortError') detail.fail(errorMessage);
      }
    },
  }));
});
