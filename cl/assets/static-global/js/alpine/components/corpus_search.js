document.addEventListener('alpine:init', () => {
  /** STORE
   * Values are shared across component instances.
   * */
  Alpine.store('corpusSearch', {
    scopeMenuExpanded: false,
    selected: '',
    keywordQuery: '',
    searchScopes: [],
    init() {
      const scopeData = document.getElementById('corpus-search-scopes');
      this.searchScopes = JSON.parse(scopeData.textContent);
      this.selected = this.searchScopes[0].label;
    },
    get selectedScope() {
      return this.searchScopes.find((scope) => scope.label === this.selected) ?? this.searchScopes[0];
    },
  });

  /** DATA
   * Each component instance has its own values.
   * */
  Alpine.data('search', () => ({
    ...createUtils(),
    advancedFiltersExpanded: false,
    advancedFiltersExpandedDesktop: false,
    get scopeMenuExpanded() {
      return this.$store.corpusSearch.scopeMenuExpanded;
    },
    get selectedScope() {
      return this.$store.corpusSearch.selectedScope;
    },
    get keywordQuery() {
      return this.$store.corpusSearch.keywordQuery;
    },
    get searchScopes() {
      return this.$store.corpusSearch.searchScopes;
    },
    get scopeCaretClass() {
      return this.scopeMenuExpanded ? 'transform rotate-180' : '';
    },
    get corpusSearchIdGroup() {
      const fieldsetIdGroup = this.searchScopes.map((scope) => `${scope.type}-fieldset`);
      return ['scope-menu', 'trigger-button', ...fieldsetIdGroup];
    },
    get corpusInputIdGroup() {
      return ['corpus-search-input'];
    },
    get fieldsetId() {
      const scope = this.searchScopes.find((scope) => scope.label === this.$el.dataset?.scope);
      return scope ? this.$id(`${scope.type}-fieldset`) : null;
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
    toggleAdvancedFiltersDesktop() {
      this.advancedFiltersExpandedDesktop = !this.advancedFiltersExpandedDesktop;
    },
    closeAdvancedFiltersDesktopIfOpen() {
      if (this.advancedFiltersExpandedDesktop) {
        this.advancedFiltersExpandedDesktop = false;
      }
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

    /**
     * Enable fieldset for selected scope, and disable the rest.
     *  */
    updateFieldsets(newSelected) {
      const updateFieldset = (scope) => {
        const fieldsetId = this.$id(`${scope.type}-fieldset`);
        const fieldsetEl = document.getElementById(fieldsetId);
        if (!fieldsetEl) return;
        if (newSelected === scope.label) fieldsetEl.removeAttribute('disabled');
        else fieldsetEl.setAttribute('disabled', 'disabled');
      };
      this.searchScopes.forEach((scope) => updateFieldset(scope));
    },

    /**
     * Disable empty fields to avoid unnecessary query params in search.
     * Also disable inputs that are within the form but flagged to be ignored (e.g. date selector radio buttons to select date type)
     *  */
    onSubmit() {
      const formInputs = Array.from(this.$el.elements).filter((el) => ['INPUT', 'SELECT'].includes(el.tagName));
      formInputs.forEach((el) => {
        const isEmpty = !el.value.trim();
        const shouldIgnore = el.dataset?.ignoreInput === 'true';
        if (isEmpty || shouldIgnore) {
          el.setAttribute('disabled', 'disabled');
        }
      });
    },

    init() {
      this.$watch('selectedScope', (newVal) => this.updateFieldsets(newVal.label));
      this.onBreakpointChange(() => {
        this.advancedFiltersExpandedDesktop = false;
      });
    },
  }));
});
