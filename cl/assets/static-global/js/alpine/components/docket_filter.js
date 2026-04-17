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
      });
    },
    submitForm() {
      const form = this.$el.closest("form") || this.$el.querySelector("form");
      if (form) form.requestSubmit();
    },
  }));
});
