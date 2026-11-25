// Value of the option that creates the typed text; no real option can carry it.
const CREATE_VALUE = Symbol('create');

document.addEventListener('alpine:init', () => {
  /**
   * Combobox for `cotton/combobox.html`.
   *
   * Reads its options from the JSON script the template renders and filters
   * them by the typed text. Selects one option, shown as the field's text, or
   * any number with the `multiple` attribute on the root, shown as removable
   * chips. The selection lives in the Alpine UI combobox on the same element.
   *
   * Events, dispatched from the root and bubbling:
   * - `combobox-add` and `combobox-remove`, with `detail.option`, after an
   *   option is selected or deselected. Replacing the single selection
   *   dispatches one of each. `detail.undo()` reverts the change without
   *   dispatching events.
   * - `combobox-create`, with `detail.label`, when the create option is chosen.
   *   Unless a listener cancels it, the typed text becomes a new selected
   *   option whose value is its label. A listener that cancels it can call
   *   `detail.add(option)` later to add and select an option of its own.
   */
  Alpine.data('combobox', () => {
    // Selection as of the last events dispatched.
    let previous = [];
    // Last text typed; outlives `query`, which empties when the list closes.
    let typed = '';

    return {
      options: [],
      initialSelection: null,
      multiple: false,
      creatable: false,
      query: '',
      createOption: { value: CREATE_VALUE, label: '' },

      /** Loads the options and the initial selection the template rendered. */
      init() {
        const script = this.$el.querySelector(':scope > script[type="application/json"]');
        const options = JSON.parse(script.textContent) ?? [];
        this.options = options.map(({ value, label }) => ({ value, label }));
        this.multiple = this.$el.hasAttribute('multiple');
        this.creatable = 'creatable' in this.$el.dataset;
        const selected = this.options.filter((_, index) => options[index].selected);
        this.initialSelection = this.multiple ? selected : (selected[0] ?? null);
        previous = selected.slice(0, this.multiple ? undefined : 1).map(({ value, label }) => ({ value, label }));
      },

      /** The options whose label contains the typed text, ignoring case. */
      get filteredOptions() {
        const query = this.query.trim().toLowerCase();
        if (!query) return this.options;
        return this.options.filter((option) => option.label.toLowerCase().includes(query));
      },

      /** Whether the typed text can become a new option: it matches no label, ignoring case, and no value. */
      get canCreate() {
        const query = this.query.trim();
        if (!this.creatable || query === '') return false;
        const lowered = query.toLowerCase();
        return !this.options.some((option) => option.label.trim().toLowerCase() === lowered || option.value === query);
      },

      /** Whether the list has nothing to offer for the typed text. */
      get isEmpty() {
        return this.filteredOptions.length === 0 && !this.canCreate;
      },

      /** The value a form submits for the single selection; empty when there is none. */
      get formValue() {
        return this.$combobox.value?.value ?? '';
      },

      /** The text the field shows for the single selection. */
      displayLabel(option) {
        return option?.label ?? '';
      },

      /** Copies the input's text into `query`. */
      syncQuery() {
        typed = this.query = this.$refs.__input.value;
      },

      /** Clears the single selection once its text has been deleted from the input. */
      clearWhenEmptied() {
        if (this.$refs.__input.value === '') this.select([]);
      },

      /** Empties the single selection and the input from the clear button, and moves focus to the input. */
      clear() {
        this.select([]);
        this.$refs.__input.value = '';
        this.query = '';
        this.$refs.__input.focus();
      },

      /** Puts back the input's own text, discarding what an input method composed in a combobox that isn't searchable. */
      restoreInput() {
        this.$refs.__input.value = this.multiple ? '' : this.displayLabel(this.$combobox.value);
      },

      /** Runs as an effect: a closed list forgets the typed text, so it reopens unfiltered. */
      clearQueryWhenClosed() {
        if (!this.$combobox.isOpen) this.query = '';
      },

      /** Shows every option again. With chips, also empties the input. */
      clearQuery() {
        if (this.multiple) this.$refs.__input.value = '';
        this.query = '';
      },

      /** Runs as an effect on the area holding the chips and the input: after the selection changes, scrolls it to its end, where the input is. */
      showInput() {
        const area = this.$el;
        if (!this.$combobox.value.length) return;
        this.$nextTick(() => {
          area.scrollTop = area.scrollHeight;
        });
      },

      /** The accessible name of a chip's remove button. */
      removeLabel(option) {
        return `Remove ${option.label}`;
      },

      /** Deselects an option from its chip and moves focus to the input. */
      remove(option) {
        const selection = this.$combobox.value;
        const index = selection.findIndex((selected) => selected.value === option.value);
        if (index !== -1) selection.splice(index, 1);
        this.$refs.__input.focus();
      },

      /** Replaces the selection with the options of the given values; only the first counts without `multiple`. */
      select(options) {
        const own = options.map((option) => this.options.find((other) => other.value === option.value) ?? option);
        if (this.multiple) this.$combobox.value.splice(0, Infinity, ...own);
        else this.$data.__value = own[0] ?? null;
      },

      /** Selects or deselects an option without dispatching events. */
      setSelected(option, selected) {
        const others = previous.filter((other) => other.value !== option.value);
        previous = selected ? [...(this.multiple ? others : []), option] : others;
        this.select(previous);
      },

      /**
       * Runs as an effect: reads the selection so any change to it re-runs
       * this, then reports the change once the current update has finished.
       */
      trackSelection() {
        const selection = [].concat(this.$combobox.value ?? []).map(({ value, label }) => ({ value, label }));
        queueMicrotask(() => this.reportSelection(selection));
      },

      /** Dispatches the events for the difference between `selection` and the last one reported. */
      reportSelection(selection) {
        if (selection.some((option) => option.value === CREATE_VALUE)) {
          this.create();
          return;
        }
        const isMissingFrom = (list) => (option) => !list.some((other) => other.value === option.value);
        const added = selection.filter(isMissingFrom(previous));
        const removed = previous.filter(isMissingFrom(selection));
        previous = selection;
        added.forEach((option) =>
          this.$dispatch('combobox-add', { option, undo: () => this.setSelected(option, false) })
        );
        removed.forEach((option) =>
          this.$dispatch('combobox-remove', { option, undo: () => this.setSelected(option, true) })
        );
        if (added.length) this.clearQuery();
      },

      /** Undoes the choice of the create option, dispatches the event and, unless cancelled, selects a new option. */
      create() {
        const label = typed.trim();
        this.select(previous);
        this.clearQuery();
        const add = ({ value, label }) => {
          const option = { value, label };
          if (!this.options.some((other) => other.value === value)) this.options.push(option);
          this.select(this.multiple ? [...previous, option] : [option]);
        };
        if (this.$dispatch('combobox-create', { label, add })) add({ value: label, label });
      },

      /** Rejects text entered in the input of a combobox that isn't searchable. */
      blockTyping(event) {
        event.preventDefault();
      },

      /** Opens or closes the list from a click on the input of a combobox that isn't searchable. */
      toggleList() {
        if (this.$combobox.isOpen) this.$data.__close();
        else this.$data.__open();
      },

      /** Opens a closed list from Enter or Space when the combobox isn't searchable, before the plugin handles the key. */
      openIfClosed(event) {
        if (this.$combobox.isOpen) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        this.$data.__open();
      },

      /** Selects the highlighted option as a click on it would; Space does this when the combobox isn't searchable. */
      selectActive() {
        this.$data.__context.activeEl()?.click();
      },

      /** Highlights the first option starting with the characters typed in quick succession when the combobox isn't searchable. */
      typeahead(event) {
        if (event.key.length !== 1 || event.key === ' ' || event.ctrlKey || event.metaKey || event.altKey) return;
        if (!this.$combobox.isOpen) this.$data.__open();
        const context = this.$data.__context;
        const key = context.searchKey(event.key.toLowerCase());
        if (key) context.activateAndScrollToKey(key, true);
      },
    };
  });
});
