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
    openDatePicker() {
      const instance = this.calendar[this.$el.dataset.date];
      if (!instance) return;
      instance.open();
    },
    closeDatePicker() {
      const instance = this.calendar[this.$el.dataset.date];
      if (!instance) return;
      instance.close();
    },
    dispatchEvent() {
      this.$dispatch(this.$el.dataset.event);
    },
    commitPickerDate(targetEl, instance) {
      targetEl.setAttribute('value', instance.input.value || '');
      targetEl.dispatchEvent(new Event('input', { bubbles: true }));
      targetEl.dispatchEvent(new Event('change', { bubbles: true }));
      instance.close();
    },
    focusFirstInput() {
      const elId = this.$el.dataset.type === 'calendar' ? this.calendarAfterInputId : this.relativeInputId;
      this.moveFocus(elId);
    },

    /**
     *  Patches the actions section of the desktop calendar card.
     *  Adds two buttons (Cancel/Apply) with their handlers.
     *  */
    _patchConfirm(instance) {
      const confirmEl = instance.calendarContainer.querySelector('.flatpickr-confirm');
      if (!confirmEl || confirmEl.dataset.patched) return;

      confirmEl.innerHTML = `
        <div class="flex gap-3 px-6 w-full pt-4 border-t border-greyscale-200">
          <button type="button" class="btn-outline flex-grow justify-center" data-action="cancel">Cancel</button>
          <button type="button" class="btn-primary flex-grow justify-center" data-action="apply">Apply</button>
        </div>
      `;
      confirmEl.dataset.patched = 'true';

      const applyBtn = confirmEl.querySelector('[data-action="apply"]');
      const cancelBtn = confirmEl.querySelector('[data-action="cancel"]');
      const targetEl = instance.config.positionElement;
      if (applyBtn) {
        applyBtn.addEventListener('click', () => this.commitPickerDate(targetEl, instance));
      }
      if (cancelBtn) {
        cancelBtn.addEventListener('click', (e) => {
          e.preventDefault();
          instance.close();
        });
      }
    },

    init() {
      const flatpickrConfig = {
        dateFormat: 'm/d/Y',
        allowInput: true,
        ariaDateFormat: 'F j, Y',
        locale: { firstDayOfWeek: 1 },
        clickOpens: false,
        closeOnSelect: false,
        disableMobile: true,
        plugins: [
          confirmDatePlugin({
            showAlways: true,
            confirmText: '',
            confirmIcon: '',
          }),
        ],
        onOpen: [
          (selectedDates, dateStr, instance) => {
            const date = instance.input.dataset?.date;
            const liveInput = date === 'after' ? this.calendarAfterInputEl : this.calendarBeforeInputEl;
            if (!liveInput.value) return;
            const liveValue = (liveInput?.value || '').trim();
            instance.setDate(liveValue, true, 'm/d/Y');
          },
        ],
      };

      const desktopFlatpickrConfig = {
        onReady: [(selectedDates, dateStr, instance) => this._patchConfirm(instance)],
        onClose: (selectedDates, dateStr, instance) => {
          instance.clear();
          instance.config.positionElement.focus();
        },
      };

      // Initialize flatpickr on next tick so all data is available
      this.$nextTick(() => {
        // DESKTOP
        // Bind flatpickr widget to hidden input to enable confirmation, but position relative to actual input
        const calendarAfterEl = document.getElementById(this.calendarAfterInputId);
        this.calendar.after = flatpickr(this.flatpickrAfterInputEl, {
          ...flatpickrConfig,
          ...desktopFlatpickrConfig,
          positionElement: calendarAfterEl,
        });
        this.flatpickrAfterInputEl.setAttribute('type', 'hidden');
        const calendarBeforeEl = document.getElementById(this.calendarBeforeInputId);
        this.calendar.before = flatpickr(this.flatpickrBeforeInputEl, {
          ...flatpickrConfig,
          ...desktopFlatpickrConfig,
          positionElement: calendarBeforeEl,
        });
        this.flatpickrBeforeInputEl.setAttribute('type', 'hidden');
      });
    },
  }));
});
