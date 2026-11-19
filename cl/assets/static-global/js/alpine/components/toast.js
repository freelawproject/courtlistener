document.addEventListener('alpine:init', () => {
  /**
   * Status toast for `cotton/toast.html`.
   *
   * Handles opening and closing of a toast, and makes sure only one toast
   * is open at a time by closing all other opened ones. This works through a
   * `window` level event. Focus is returned to its trigger when corresponding.
   * AT content announcement is triggered by swapping contents of its
   * `role="status"` live region already present in the document.
   * */
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
          this.$refs.live.append(this.$refs.message.content.cloneNode(true));
        } else {
          this.$refs.live.replaceChildren();
        }
      });
    },
    /** Opens this toast, first "making way" for itself with a synchronous broadcast event for other toasts to close. */
    open() {
      this.$dispatch('toast-opened');
      // Re-opening keeps the original opener: focus may now be inside the toast itself.
      if (!this.isOpen) {
        this.opener = this.activeElementOrTrigger();
      }
      this.isOpen = true;
    },
    /** The focused element, or the trigger's first control when a click left <body> active. */
    activeElementOrTrigger() {
      const active = document.activeElement;
      if (active && active !== document.body) {
        return active;
      }
      const controls = this.$root.querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      return [...controls].find((el) => !this.$refs.region.contains(el)) ?? null;
    },
    /** Handles 'toast-opened' events to close itself if another one opened */
    onToastOpened(event) {
      if (this.isOpen && !this.$root.contains(event.target)) {
        this.close();
      }
    },
    /** Closes this toast and moves focus back to its trigger if it was inside the toast contents. */
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
