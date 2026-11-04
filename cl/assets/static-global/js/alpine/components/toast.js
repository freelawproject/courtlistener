document.addEventListener('alpine:init', () => {
  Alpine.data('toast', () => ({
    isOpen: false,
    /** Element focused when the toast opened, so closing it from the keyboard does not drop focus to the body. */
    opener: null,
    open() {
      // One message at a time: every other open toast on the page closes first,
      // so the opener recorded below is never inside a toast that just closed.
      this.$dispatch('toast-opened');
      // Re-opening keeps the original opener: focus may now be inside the toast itself.
      if (!this.isOpen) {
        this.opener = document.activeElement;
      }
      this.isOpen = true;
    },
    /** Closes this toast when another one opens. */
    replace(event) {
      if (this.isOpen && !this.$root.contains(event.target)) {
        this.close();
      }
    },
    close() {
      const region = this.$root.querySelector('[role="status"]');
      const focusWasInside = region.contains(document.activeElement);
      this.isOpen = false;
      if (focusWasInside && this.opener?.isConnected) {
        this.opener.focus({ preventScroll: true });
      }
      this.opener = null;
    },
  }));
});
