document.addEventListener('alpine:init', () => {
  Alpine.data('dateSelector', () => ({
    ...createFocus(),
    dropdownMenuOpen: true,
    dateAfterRelative: '',
    dateBefore: '',
    selectedType: 'calendar',
    get dateSelectorIdGroup() {
      return ['type-select', 'relative-dates-menu', 'label', 'relative-input', 'calendar-after-input'];
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
    get relativeInputId() {
      return this.$id('relative-input');
    },
    get calendarInputId() {
      return this.$id('calendar-after-input');
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
    toggleDropdownMenu() {
      this.dropdownMenuOpen = !this.dropdownMenuOpen;
    },
    selectRelativeDate() {
      this.dateAfterRelative = this.$el.dataset.value;
      this.closeDropdownMenu();
    },
    selectDateType() {
      this.selectedType = this.$el.value;
    },
    focusFirstInput() {
      const elId = this.$el.dataset.type === 'calendar' ? this.calendarInputId : this.relativeInputId;
      this.moveFocus(elId);
    },
  }));
});
