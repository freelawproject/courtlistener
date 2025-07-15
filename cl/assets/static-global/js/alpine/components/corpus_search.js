document.addEventListener('alpine:init', () => {
  Alpine.store('corpusSearch', {
    scopeMenuExpanded: false,
    selected: 'Case Law',
    searchScopes: [
      { label: 'Case Law', type: 'o', shortDescription: '10M+ Opinions', fieldset: 'o-fieldset' },
      { label: 'RECAP Archive', type: 'r', shortDescription: '500M+ Records', fieldset: 'r-fieldset' },
      { label: 'Oral Arguments', type: 'oa', shortDescription: '90k+ Audio Files', fieldset: 'oa-fieldset' },
      { label: 'Judges', type: 'p', shortDescription: '15k+ Profiles', fieldset: 'p-fieldset' },
    ],
    get selectedScope() {
      const index = this.searchScopes.findIndex((scope) => scope.label === this.selected);
      if (index === -1) return 'o';
      return this.searchScopes[index];
    },
  });
  Alpine.data('search', () => ({
    get scopeMenuExpanded() {
      return this.$store.corpusSearch.scopeMenuExpanded;
    },
    get selectedScope() {
      return this.$store.corpusSearch.selected;
    },
    get selectedScopeType() {
      return this.$store.corpusSearch.selectedScope.type;
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
    get isActiveScope() {
      return this.$el.dataset?.scope === this.$store.corpusSearch.selected;
    },
    get triggerButtonId() {
      return this.$id('trigger-button');
    },
    get triggerButtonElement() {
      return document.getElementById(this.triggerButtonId);
    },
    get scopeTabClass() {
      return this.isActiveScope ? 'font-semibold text-greyscale-900' : 'font-medium text-greyscale-700';
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
