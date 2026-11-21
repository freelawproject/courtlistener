document.addEventListener('alpine:init', () => {
  Alpine.data('dateSelector', () => ({
    ...createFocus(),
    ...createDatePicker(),
    dropdownMenuOpen: true,
    dateAfterRelative: '',
    selectedType: 'calendar',
    get dateSelectorIdGroup() {
      return [
        'type-select',
        'relative-dates-menu',
        'label',
        'relative-input',
        'relative-option',
        'calendar-input',
      ];
    },
    get typeSelectName() {
      return this.$id('type-select');
    },
    get relativeDatesMenuId() {
      return this.$id('relative-dates-menu');
    },
    get labelId() {
      return this.$id('label');
    },
    get relativeOptionIds() {
      return {
        '1d ago': `1d-${this.$id('relative-option')}`,
        '7d ago': `7d-${this.$id('relative-option')}`,
        '14d ago': `14d-${this.$id('relative-option')}`,
        '1m ago': `1m-${this.$id('relative-option')}`,
        '3m ago': `3m-${this.$id('relative-option')}`,
        '6m ago': `6m-${this.$id('relative-option')}`,
        '1y ago': `1y-${this.$id('relative-option')}`,
      };
    },
    get relativeOptionId() {
      const val = this.$el.dataset?.value;
      return val ? this.relativeOptionIds[val] : undefined;
    },
    get relativeInputId() {
      return this.$id('relative-input');
    },
    get calendarInputId() {
      return this.$id('calendar-input', this.$el.dataset.date);
    },
    get isSelectedType() {
      return this.$el.dataset.type === this.selectedType;
    },
    get disabled() {
      return this.isSelectedType ? undefined : true;
    },
    get isSelectedRelativeDate() {
      return this.$el.dataset.value === this.dateAfterRelative;
    },
    closeDropdownMenu() {
      this.dropdownMenuOpen = false;
    },
    openDropdownMenu() {
      this.dropdownMenuOpen = true;
    },
    onComboboxEscape() {
      if (this.dropdownMenuOpen) this.closeDropdownMenu();
      else this.dateAfterRelative = '';
    },
    enterDropdownFocus() {
      if (!this.dropdownMenuOpen) this.dropdownMenuOpen = true;
      this.$nextTick(() => {
        if (Object.keys(this.relativeOptionIds).includes(this.dateAfterRelative)) {
          this.moveFocus(this.relativeOptionIds[this.dateAfterRelative]);
        } else {
          this.moveFocus(this.relativeOptionIds['1d ago']);
        }
      });
    },
    toggleDropdownMenu() {
      this.dropdownMenuOpen = !this.dropdownMenuOpen;
    },
    focusRelativeInput() {
      this.moveFocus(this.relativeInputId);
      this.$nextTick(() => {
        if (this.dropdownMenuOpen) this.closeDropdownMenu();
      });
    },
    updateDateAfterRelative() {
      this.dateAfterRelative = this.$el.value;
      if (this.dropdownMenuOpen) this.closeDropdownMenu();
    },
    selectRelativeDate() {
      this.dateAfterRelative = this.$el.dataset.value;
      this.focusRelativeInput();
    },
    selectDateType() {
      this.selectedType = this.$el.value;
    },
    dispatchEvent() {
      this.$dispatch(this.$el.dataset.event);
    },
    focusFirstInput() {
      const elId = this.$el.dataset.type === 'calendar' ? this.$id('calendar-input', 'after') : this.relativeInputId;
      this.moveFocus(elId);
    },

    init() {
      // Initialize on next tick so all data is available
      this.$nextTick(() => this.initDatePickers(this.$el));
    },
  }));
});
