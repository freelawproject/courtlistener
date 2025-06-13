document.addEventListener('alpine:init', () => {
  Alpine.store('corpusSearch', {
    scopeMenuExpanded: false,
    selected: 'Case Law',
    searchScopes: [{ label: 'Case Law' }, { label: 'RECAP Archive' }, { label: 'Oral Arguments' }, { label: 'Judges' }],
  });
  Alpine.data('search', () => ({
    get scopeMenuExpanded() {
      return this.$store.corpusSearch.scopeMenuExpanded;
    },
    get selectedScope() {
      return this.$store.corpusSearch.selected;
    },
    get searchScopes() {
      return this.$store.corpusSearch.searchScopes;
    },
    get scopeCaretClass() {
      return this.scopeMenuExpanded ? 'transform rotate-180' : '';
    },
    toggleScopeMenu() {
      this.$store.corpusSearch.scopeMenuExpanded = !this.$store.corpusSearch.scopeMenuExpanded;
    },
    closeScopeMenu() {
      this.$store.corpusSearch.scopeMenuExpanded = false;
    },
    selectScope() {
      this.$store.corpusSearch.selected = this.$el.dataset?.scope;
      this.$store.corpusSearch.scopeMenuExpanded = false;
      const searchInput = document.getElementById("header-search-bar");
      this.$focus.focus(searchInput);
    },
    isActiveScope() {
      return this.$el.dataset?.scope === this.$store.corpusSearch.selected;
    },
  }));
});
