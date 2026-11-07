// How far the arrow's centre sits outside the bubble: half of
// tooltip_arrow.svg's 8.5px height minus the 2.5px that overlaps the bubble.
const ARROW_OUTSIDE = 1.75;

document.addEventListener('alpine:init', () => {
  /**
   * Help-icon toggletip for `cotton/tooltip.html`.
   *
   * Hovering shows the message; clicking, tapping, Enter or Space pins it
   * open. Escape, a click outside, or focus leaving the component closes it.
   * The message is copied into a live region on open so screen readers
   * announce it.
   */
  Alpine.data('tooltip', () => ({
    hovered: false,
    pinned: false,
    hideTimer: null,

    /** Whether the tooltip is showing, from hover or from a pin. */
    get isOpen() {
      return this.hovered || this.pinned;
    },

    /** Shows or removes the message whenever the tooltip opens or closes. */
    init() {
      this.$watch('isOpen', (open) => {
        if (!open) {
          this.$refs.live.replaceChildren();
          return;
        }
        // The live region is empty while closed, so this is new content and
        // screen readers announce it.
        this.$refs.live.append(this.$refs.message.content.cloneNode(true));
        this.placeArrow();
      });
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

    /**
     * Points the arrow at the button from whichever side the tooltip landed
     * on. `x-effect` passes `$anchor`, so this re-runs on every move.
     */
    placeArrow(anchor) {
      // Reading the position makes x-effect re-run whenever it changes.
      anchor?.x;
      anchor?.y;

      // The arrow is a copy Alpine never initialised, so it's styled here.
      const arrow = this.$refs.live.querySelector('[data-arrow]');
      if (!arrow) return;

      const button = this.$refs.trigger.getBoundingClientRect();
      const bubble = this.$refs.live.getBoundingClientRect();
      const x = button.left + button.width / 2 - bubble.left;
      const y = button.top + button.height / 2 - bubble.top;

      // The SVG points down; rotate it toward the button.
      let left = x;
      let top = bubble.height + ARROW_OUTSIDE;
      let rotation = 0;
      if (bubble.top >= button.bottom) {
        [top, rotation] = [-ARROW_OUTSIDE, 180];
      } else if (bubble.right <= button.left) {
        [left, top, rotation] = [bubble.width + ARROW_OUTSIDE, y, -90];
      } else if (bubble.left >= button.right) {
        [left, top, rotation] = [-ARROW_OUTSIDE, y, 90];
      }

      Object.assign(arrow.style, {
        left: `${left}px`,
        top: `${top}px`,
        transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
      });
    },
  }));
});
