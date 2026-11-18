document.addEventListener('alpine:init', () => {
  /**
   * Status toast for `cotton/toast.html`.
   *
   * `open()` shows it; only one toast is open at a time. On each opening the
   * message is copied into a new `role="status"` region, two frames after the
   * region exists: screen readers announce content added to a region already
   * in the tree, and VoiceOver goes silent on a region reused for the same
   * text. Focus never moves to the toast; closing it from inside returns
   * focus to the element that opened it.
   */
  Alpine.data('toast', () => ({
    isOpen: false,
    opener: null,
    /** Applied only while open, so a closed toast paints nothing and takes no clicks. */
    get panelClass() {
      return this.isOpen ? 'pointer-events-auto bg-greyscale-900 py-2 pl-2.5 pr-3 shadow-lg' : '';
    },
    init() {
      this.$watch('isOpen', (open) => {
        if (open) {
          this.showMessage();
        } else {
          this.$refs.live.replaceChildren();
        }
      });
    },
    showMessage() {
      const region = document.createElement('div');
      region.setAttribute('role', 'status');
      this.$refs.live.replaceChildren(region);
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (region.isConnected) {
            region.append(this.$refs.message.content.cloneNode(true));
          }
        });
      });
    },
    open() {
      // Other toasts close first, so the opener recorded below is never inside one.
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
      const focusWasInside = this.$refs.region.contains(document.activeElement);
      this.isOpen = false;
      if (focusWasInside && this.opener?.isConnected) {
        this.opener.focus({ preventScroll: true });
      }
      this.opener = null;
    },
  }));
});
