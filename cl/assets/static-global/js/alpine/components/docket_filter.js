document.addEventListener("alpine:init", () => {
  Alpine.data("docketFilter", () => ({
    init() {
      this.$nextTick(() => {
        const config = {
          dateFormat: "m/d/Y",
          allowInput: true,
          ariaDateFormat: "F j, Y",
        };
        const afterEl = this.$el.querySelector("[data-flatpickr-after]");
        const beforeEl = this.$el.querySelector("[data-flatpickr-before]");
        if (afterEl) flatpickr(afterEl, config);
        if (beforeEl) flatpickr(beforeEl, config);
      });
    },
    submitForm() {
      const form = this.$el.closest("form") || this.$el.querySelector("form");
      if (form) form.requestSubmit();
    },
  }));
});
