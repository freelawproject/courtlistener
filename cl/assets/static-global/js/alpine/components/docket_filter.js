document.addEventListener("alpine:init", () => {
  Alpine.data("docketFilter", () => ({
    init() {
      this.$nextTick(() => {
        // If the filter form was submitted with errors, pop the mobile
        // drawer open so the user can see the validation messages inside.
        const drawer = this.$el.querySelector("[data-has-errors]");
        if (drawer) {
          drawer.dispatchEvent(new CustomEvent("open-filter-drawer"));
        }
      });
    },
    // Mirror the legacy base.js search behavior: append user-typed text to a
    // pre-baked docket-scoped search URL and navigate. Guards against empty
    // input (no trailing space when user typed nothing).
    submitDocketSearch(refName, docketPk) {
      const input = this.$refs[refName];
      const userText = (input?.value || "").trim();
      const base = `/?type=r&q=docket_id:${docketPk}`;
      window.location = userText ? `${base} ${userText}` : base;
    },
    submitForm(event) {
      const form = event.target.closest("form");
      if (form) form.requestSubmit();
    },
  }));
});
