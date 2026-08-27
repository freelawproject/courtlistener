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
  }));
});
