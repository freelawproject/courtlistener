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
    get corpusSearchIdGroup() {
      return ['scope-menu', 'corpus-search-input', 'trigger-button'];
    },
    get menuId() {
      return this.$id('scope-menu');
    },
    get scopeMenuElement() {
      return document.getElementById(this.menuId);
    },
    get inputId() {
      return this.$id('corpus-search-input');
    },
    get inputElement() {
      return document.getElementById(this.inputId);
    },
    get triggerButtonId() {
      return this.$id('trigger-button');
    },
    get triggerButtonElement() {
      return document.getElementById(this.triggerButtonId);
    },
    openScopeMenu() {
      this.$store.corpusSearch.scopeMenuExpanded = true;
      this.$focus.within(this.scopeMenuElement).first();
    },
    closeScopeMenu() {
      this.$store.corpusSearch.scopeMenuExpanded = false;
      this.$focus.focus(this.inputElement);
    },
    closeScopeMenuBack() {
      this.$store.corpusSearch.scopeMenuExpanded = false;
      this.$focus.focus(this.triggerButtonElement);
    },
    selectScope() {
      this.$store.corpusSearch.selected = this.$el.dataset?.scope;
      this.closeScopeMenu();
    },
    isActiveScope() {
      return this.$el.dataset?.scope === this.$store.corpusSearch.selected;
    },
  }));
});
