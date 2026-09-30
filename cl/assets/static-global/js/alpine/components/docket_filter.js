document.addEventListener("alpine:init", () => {
  Alpine.data("docketFilter", () => ({
    init() {
      this.$nextTick(() => {
        const config = {
          dateFormat: "m/d/Y",
          allowInput: true,
          ariaDateFormat: "F j, Y",
        };
        for (const el of this.$el.querySelectorAll("[data-flatpickr-after], [data-flatpickr-before]")) {
          flatpickr(el, config);
          // With `allowInput`, flatpickr's own keydown handler on this input
          // commits a typed date on Enter, closes the calendar, and blurs the
          // input before returning. That blur happens mid-keydown, so the
          // browser's implicit form submission never fires, and flatpickr's
          // `onKeyDown` config hook is skipped on that path too. This listener
          // is registered after flatpickr's on the same element, so it runs
          // once the value is normalized and the calendar is closed. Only
          // the date inputs need it: the other fields, in both the desktop
          // and the mobile drawer forms, already submit on Enter through
          // the browser's implicit submission.
          el.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") return;
            el.form?.requestSubmit();
          });
        }

        // If the filter form was submitted with errors, pop the mobile
        // drawer open so the user can see the validation messages inside.
        const drawer = this.$el.querySelector("[data-has-errors]");
        if (drawer) {
          drawer.dispatchEvent(new CustomEvent("open-filter-drawer"));
        }
      });
    },
    submitForm(event) {
      const form = event.target.closest("form");
      if (form) form.requestSubmit();
    },
    /**
     * Merge all typed search terms into the final hidden `q` input so the search
     * stays scoped to the docket, in the same shape as build_docket_id_q_param.
     * The scope is read from `data-docket-scope` rather than from the hidden
     * input: assigning a hidden input's value rewrites its attribute, and back
     * navigation restores that DOM, so a second submit would wrap the previous
     * query again.
     */
    buildScopedQueryOnSubmit(event) {
      const form = event.target;
      const scope = this.$root.dataset.docketScope;
      const terms = form.querySelector("[data-search-terms]").value.trim();
      form.querySelector('input[name="q"]').value = terms ? `(${terms}) AND ${scope}` : scope;
    },
  }));
});
