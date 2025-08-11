const fieldsetIdSeeds = {
  opinions: 'o-fieldset',
  recap: 'r-fieldset',
  oralArgs: 'oa-fieldset',
  judges: 'p-fieldset',
};

document.addEventListener('alpine:init', () => {
  Alpine.store('corpusSearch', {
    scopeMenuExpanded: false,
    selected: 'Case Law',
    keywordQuery: '',
    searchScopes: [
      {
        label: 'Case Law',
        type: 'o',
        shortDescription: '10M+ Opinions',
        fieldset: fieldsetIdSeeds['opinions'],
      },
      {
        label: 'RECAP Archive',
        type: 'r',
        shortDescription: '500M+ Records',
        fieldset: fieldsetIdSeeds['recap'],
      },
      {
        label: 'Oral Arguments',
        type: 'oa',
        shortDescription: '90k+ Audio Files',
        fieldset: fieldsetIdSeeds['oralArgs'],
      },
      {
        label: 'Judges',
        type: 'p',
        shortDescription: '15k+ Profiles',
        fieldset: fieldsetIdSeeds['judges'],
      },
    ],
    get selectedScope() {
      const index = this.searchScopes.findIndex((scope) => scope.label === this.selected);
      if (index === -1) return 'o';
      return this.searchScopes[index];
    },
  });
  Alpine.data('search', () => ({
    advancedFiltersExpanded: false,
    get scopeMenuExpanded() {
      return this.$store.corpusSearch.scopeMenuExpanded;
    },
    get selectedScope() {
      return this.$store.corpusSearch.selected;
    },
    get keywordQuery() {
      return this.$store.corpusSearch.keywordQuery;
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
      const fieldsetIdGroup = [
        fieldsetIdSeeds['opinions'],
        fieldsetIdSeeds['recap'],
        fieldsetIdSeeds['oralArgs'],
        fieldsetIdSeeds['judges'],
      ];
      return ['scope-menu', 'trigger-button', ...fieldsetIdGroup];
    },
    get corpusInputIdGroup() {
      return ['corpus-search-input'];
    },
    get fieldsetIds() {
      return {
        opinions: this.$id(fieldsetIdSeeds['opinions']),
        recap: this.$id(fieldsetIdSeeds['recap']),
        oralArgs: this.$id(fieldsetIdSeeds['oralArgs']),
        judges: this.$id(fieldsetIdSeeds['judges']),
      };
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
      const baseClass =
        'min-w-41 h-[58px] text-sm font-normal rounded-t-2xl text-greyscale-600 flex justify-center items-center';
      return this.isActiveScope ? `${baseClass} bg-white` : `${baseClass} bg-greyscale-50`;
    },
    get scopeTabTitleClass() {
      return this.isActiveScope ? 'font-semibold text-greyscale-900' : 'font-medium text-greyscale-700';
    },
    get advancedFiltersCollapsed() {
      return !this.advancedFiltersExpanded;
    },
    updateKeyword(event) {
      this.$store.corpusSearch.keywordQuery = event.target.value;
    },
    toggleAdvancedFilters() {
      this.advancedFiltersExpanded = !this.advancedFiltersExpanded;
    },
    openAdvancedFilters() {
      this.advancedFiltersExpanded = true;
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
    updateFieldsets(newSelected) {
      const updateFieldset = (scope) => {
        const fieldsetId = this.$id(scope.fieldset);
        const fieldsetEl = document.getElementById(fieldsetId);
        if (!fieldsetEl) return;
        if (newSelected === scope.label) fieldsetEl.removeAttribute('disabled');
        else fieldsetEl.setAttribute('disabled', 'disabled');
      };
      this.searchScopes.forEach((scope) => updateFieldset(scope));
    },
    onSubmit() {
      Array.from(this.$el.elements).forEach((el) => {
        const isInput = ['INPUT', 'SELECT'].includes(el.tagName);
        if (isInput && !el.value.trim()) {
          el.setAttribute('disabled', 'disabled');
        }
      });
    },
    init() {
      this.$watch('selectedScope', (newVal) => this.updateFieldsets(newVal));
    },
  }));
});
