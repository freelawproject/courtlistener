document.addEventListener('alpine:init', () => {
  Alpine.data('dateSelector', () => ({
    ...createFocus(),
    dropdownMenuOpen: true,
    dateAfterRelative: '',
    selectedType: 'calendar',
    calendar: { after: null, before: null },
    get dateSelectorIdGroup() {
      return [
        'type-select',
        'relative-dates-menu',
        'label',
        'relative-input',
        'relative-option',
        'calendar-after-input',
        'calendar-before-input',
        'flatpickr-after-input',
        'flatpickr-before-input',
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
    get calendarAfterInputId() {
      return this.$id('calendar-after-input');
    },
    get calendarBeforeInputId() {
      return this.$id('calendar-before-input');
    },
    get calendarAfterInputEl() {
      return document.getElementById(this.calendarAfterInputId);
    },
    get calendarBeforeInputEl() {
      return document.getElementById(this.calendarBeforeInputId);
    },
    get flatpickrAfterInputId() {
      return this.$id('flatpickr-after-input');
    },
    get flatpickrBeforeInputId() {
      return this.$id('flatpickr-before-input');
    },
    get flatpickrAfterInputEl() {
      return document.getElementById(this.flatpickrAfterInputId);
    },
    get flatpickrBeforeInputEl() {
      return document.getElementById(this.flatpickrBeforeInputId);
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
      const elId = this.$el.dataset.type === 'calendar' ? this.calendarAfterInputId : this.relativeInputId;
      this.moveFocus(elId);
    },

    init() {
      // Initialize flatpickr on next tick so all data is available
      this.$nextTick(() => {
        // Bind each picker to a hidden input for confirmation, but position it
        // relative to its visible input.
        const inputs = [
          ['after', this.flatpickrAfterInputEl, this.calendarAfterInputEl],
          ['before', this.flatpickrBeforeInputEl, this.calendarBeforeInputEl],
        ];
        for (const [direction, hiddenInput, positionElement] of inputs) {
          this.calendar[direction] = createConfirmedDatePicker(hiddenInput, positionElement);
        }
      });
    },
    destroy() {
      for (const picker of Object.values(this.calendar)) picker?.destroy();
    },
  }));
});
