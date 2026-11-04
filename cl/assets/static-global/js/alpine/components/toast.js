document.addEventListener('alpine:init', () => {
  Alpine.data('toast', () => ({
    isOpen: false,
    /** Element focused when the toast opened, so closing it from the keyboard does not drop focus to the body. */
    opener: null,
    open() {
      // Re-opening keeps the original opener: focus may now be inside the toast itself.
      if (!this.isOpen) {
        this.opener = document.activeElement;
      }
      this.isOpen = true;
      // One message at a time: every other open toast on the page closes.
      this.$root.dispatchEvent(new CustomEvent('toast-opened', { bubbles: true }));
    },
    /** Closes this toast when another one opens. */
    replace(event) {
      if (event.target !== this.$root && this.isOpen) {
        this.close();
      }
    },
    close() {
      const focusWasInside = this.$root.contains(document.activeElement);
      this.isOpen = false;
      if (focusWasInside && this.opener?.isConnected) {
        this.opener.focus({ preventScroll: true });
      }
      this.opener = null;
    },
  }));
});
