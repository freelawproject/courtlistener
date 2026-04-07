document.addEventListener("alpine:init", () => {
  Alpine.data("filterDrawer", () => ({
    ...createUtils(),
    isOpen: false,
    open() {
      this.isOpen = true;
    },
    close() {
      this.isOpen = false;
    },
    get drawerId() {
      return this.$id("filter-drawer");
    },
    get drawerIdGroup() {
      return ["filter-drawer"];
    },
    init() {
      if (this.$el.dataset.hasErrors !== undefined) this.open();
      this.onBreakpointChange((e) => {
        if (e.matches && this.isOpen) {
          this.close();
        }
      });
    },
  }));
});
