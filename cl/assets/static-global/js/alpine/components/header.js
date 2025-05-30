document.addEventListener('alpine:init', () => {
  Alpine.data('header', () => ({
    profileMenuExpanded: false,
    scopeMenuExpanded: false,
    supportMenuExpanded: false,
    selected: 'Case Law',
    searchScopes: [{ label: 'Case Law' }, { label: 'RECAP Archive' }, { label: 'Oral Arguments' }, { label: 'Judges' }],
    get profileCaretClass() {
      return this.profileMenuExpanded ? 'transform rotate-180' : '';
    },
    get scopeCaretClass() {
      return this.scopeMenuExpanded ? 'transform rotate-180' : '';
    },
    toggleSupportMenu() {
      this.supportMenuExpanded = !this.supportMenuExpanded;
    },
    closeSupportMenu() {
      this.supportMenuExpanded = false;
    },
    toggleProfileMenu() {
      this.profileMenuExpanded = !this.profileMenuExpanded;
    },
    closeProfileMenu() {
      this.profileMenuExpanded = false;
    },
    toggleScopeMenu() {
      this.scopeMenuExpanded = !this.scopeMenuExpanded;
    },
    closeScopeMenu() {
      this.scopeMenuExpanded = false;
    },
    selectScope() {
      this.selected = this.$el.dataset?.scope;
      this.scopeMenuExpanded = false;
      const searchInput = document.getElementById("header-search-bar");
      this.$focus.focus(searchInput);
    },
    isActiveScope() {
      return this.$el.dataset?.scope === this.selected;
    },
  }));
});
