document.addEventListener('alpine:init', () => {
  Alpine.data('dialog', () => ({
    ...createUtils(),
    isOpen: false,
    open() {
      this.isOpen = true;
    },
    close() {
      this.isOpen = false;
    },
    toggle() {
      this.isOpen = !this.isOpen;
    },
    get dialogElement() {
      return document.getElementById(this.dialogId);
    },
    get dialogId() {
      return this.$id('dialog');
    },
    get dialogIdGroup() {
      return ['dialog'];
    },
    init() {
      const callback = (e) => {
        if (e.matches && this.isOpen) {
          this.close();
        }
      };
      this.onBreakpointChange(callback);
    },
  }));
});
