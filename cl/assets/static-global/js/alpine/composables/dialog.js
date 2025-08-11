document.addEventListener('alpine:init', () => {
  Alpine.data('dialog', () => ({
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
      const mobileBreakpoint = getComputedStyle(document.documentElement)
        .getPropertyValue('--mobile-breakpoint')
        .trim();
      const mediaQuery = window.matchMedia(`(min-width: ${mobileBreakpoint})`);
      mediaQuery.addEventListener('change', (e) => {
        if (e.matches && this.isOpen) {
          this.close();
        }
      });
    },
  }));
});
