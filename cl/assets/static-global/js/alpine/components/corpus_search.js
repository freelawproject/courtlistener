const fieldsetIdSeeds = {
  opinions: 'o-fieldset',
  recap: 'r-fieldset',
  oralArgs: 'oa-fieldset',
  judges: 'p-fieldset',
};

/**
 * Returns true when filters are set and will be applied on submit.
 * Uses `:disabled` pseudo-class to identify elements that are turned off.
 * Checkboxes only count when checked.
 * Ignores whitespace-only values.
 */
const willBeSubmitted = (el) => {
  if (el.matches(':disabled') || el.dataset?.ignoreInput === 'true') return false;
  if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
  return !!el.value.trim();
};
/**
 * Returns true when a submitted control is a user-set filter. Excludes the
 * hidden inputs carrying search state (`q`, `type`) and the unnamed inputs the
 * keyword field and the date pickers use internally.
 */
const isActiveFilter = (el) => !!el.name && el.type !== 'hidden' && willBeSubmitted(el);

document.addEventListener('alpine:init', () => {
  /** STORE
   * Values are shared across component instances.
   * */
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

  /** DATA
   * Each component instance has its own values.
   * */
  Alpine.data('search', () => ({
    ...createUtils(),
    advancedFiltersExpanded: false,
    advancedFiltersExpandedDesktop: false,
    activeFilterCount: 0,
    // Guaranteed to be the x-data root
    formEl: null,
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
    get formInputs() {
      return Array.from(this.formEl.elements).filter((el) => ['INPUT', 'SELECT'].includes(el.tagName));
    },
    get hasActiveFilters() {
      return this.activeFilterCount > 0;
    },
    get activeFilterCountLabel() {
      return `(${this.activeFilterCount})`;
    },
    get filtersButtonAriaLabel() {
      return this.hasActiveFilters ? `Filters, ${this.activeFilterCount} active` : 'Filters';
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
        const fieldsetId = this.$id(scope.fieldset);
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
      this.formInputs.filter((el) => !willBeSubmitted(el)).forEach((el) => el.setAttribute('disabled', 'disabled'));
    },

    /**
     * Recount the filters the next submit would apply, so the count can be shown
     * before submitting.
     */
    updateActiveFilterCount() {
      this.activeFilterCount = this.formInputs.filter(isActiveFilter).length;
    },

    init() {
      // Save the x-data root on initialization
      this.formEl = this.$el;
      this.$watch('selectedScope', (newVal) => {
        this.updateFieldsets(newVal.label);
        this.updateActiveFilterCount();
      });
      this.onBreakpointChange(() => {
        this.advancedFiltersExpandedDesktop = false;
      });
      this.updateActiveFilterCount();
    },
  }));
});
