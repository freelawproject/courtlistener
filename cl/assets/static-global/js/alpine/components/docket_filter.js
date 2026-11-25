document.addEventListener("alpine:init", () => {
  Alpine.data("docketFilter", () => ({
    datePickers: [],
    init() {
      this.$nextTick(() => {
        for (const hidden of this.$el.querySelectorAll('[data-confirmed-date-picker]')) {
          const input = hidden.parentElement.querySelector('input[data-flatpickr-after], input[data-flatpickr-before]');
          if (!input) continue;
          // Docket filters have historically allowed future dates.
          this.datePickers.push(createConfirmedDatePicker(hidden, input, { allowFuture: true }));
        }

        // If the filter form was submitted with errors, open the mobile
        // dialog so the filters are in view. Only below the mobile
        // breakpoint: above it the dialog is hidden, and opening it would
        // leave an invisible modal open.
        const breakpoint = getComputedStyle(document.documentElement)
          .getPropertyValue("--mobile-breakpoint")
          .trim();
        const isMobile = !window.matchMedia(`(min-width: ${breakpoint})`).matches;
        if ("hasErrors" in this.$el.dataset && isMobile) {
          window.dispatchEvent(new CustomEvent("open-filter-dialog"));
        }
      });
    },
    destroy() {
      for (const picker of this.datePickers) picker.destroy();
    },
    submitForm(event) {
      const form = event.target.closest("form");
      if (form) form.requestSubmit();
    },
    /**
     * Drop empty fields from a filter form's submission, so the URL only
     * carries the filters that are set. `formdata` fires on every submit
     * path: the Apply button, implicit submission, and requestSubmit().
     */
    dropEmptyParams(event) {
      for (const [name, value] of [...event.formData]) {
        if (value === "") event.formData.delete(name);
      }
    },
    /**
     * Merge all typed search terms into the final hidden `q` input so the search
     * stays scoped to the docket, in the same shape as build_docket_id_q_param.
     * The scope is read from `data-docket-scope` rather than from the hidden
     * input: assigning a hidden input's value rewrites its attribute, and back
     * navigation restores that DOM, so a second submit would wrap the previous
     * query again. It's looked up with closest() rather than `$root`, which
     * resolves to the nearest x-data element: inside the mobile dialog, that
     * is the dialog's own root, not the docketFilter one.
     */
    buildScopedQueryOnSubmit(event) {
      const form = event.target;
      const scope = form.closest("[data-docket-scope]").dataset.docketScope;
      const terms = form.querySelector("[data-search-terms]").value.trim();
      form.querySelector('input[name="q"]').value = terms ? `(${terms}) AND ${scope}` : scope;
    },
  }));
});
