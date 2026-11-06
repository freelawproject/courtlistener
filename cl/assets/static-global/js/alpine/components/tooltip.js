document.addEventListener('alpine:init', () => {
  /**
   * Help-icon toggletip for `cotton/tooltip.html`.
   *
   * Hovering shows the message; clicking, tapping, Enter or Space pins it
   * open. Escape, a click outside, or focus leaving the component closes it.
   */
  Alpine.data('tooltip', () => ({
    hovered: false,
    pinned: false,
    hideTimer: null,

    /** Whether the tooltip is showing, from hover or from a pin. */
    get isOpen() {
      return this.hovered || this.pinned;
    },

    /** Opens on hover, cancelling a hide that is still waiting. */
    show() {
      clearTimeout(this.hideTimer);
      this.hovered = true;
    },

    /** Ends the hover state after a delay; a pinned tooltip stays open. */
    scheduleHide() {
      // The delay lets the pointer cross the gap between the button and the
      // tooltip without it closing (WCAG 1.4.13: hover content stays hoverable).
      this.hideTimer = setTimeout(() => {
        this.hovered = false;
      }, 200);
    },

    /**
     * Pins or unpins the tooltip. Unpinning also ends the hover state, so the
     * second click closes it even while the pointer is still on the button.
     */
    togglePin() {
      this.pinned = !this.pinned;
      if (!this.pinned) this.hovered = false;
    },

    /** Closes the tooltip whether it was opened by hover or pinned. */
    hide() {
      this.hovered = false;
      this.pinned = false;
    },

    /**
     * Closes the tooltip when focus moves outside the component, so it never
     * covers the next focused element and reopening announces it again.
     */
    hideOnFocusOut(event) {
      if (!this.$root.contains(event.relatedTarget)) this.hide();
    },
  }));
});
