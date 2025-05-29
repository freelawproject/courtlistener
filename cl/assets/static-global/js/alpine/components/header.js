document.addEventListener('alpine:init', () => {
  Alpine.data('header', () => ({
    profileMenuExpanded: false,
    scopeMenuExpanded: false,
    selected: 'Case Law',
    searchScopes: [{ label: 'Case Law' }, { label: 'RECAP Archive' }, { label: 'Oral Arguments' }, { label: 'Judges' }],
    get profileCaretClass() {
      return this.profileMenuExpanded ? 'transform rotate-180' : '';
    },
    get scopeCaretClass() {
      return this.scopeMenuExpanded ? 'transform rotate-180' : '';
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
    },
    isActiveScope() {
      return this.$el.dataset?.scope === this.selected;
    },
  }));
});
