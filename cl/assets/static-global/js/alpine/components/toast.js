document.addEventListener('alpine:init', () => {
  /** Alpine hands methods different proxies of a component, so toasts are told apart by their root element. */
  const same = (a, b) => a.$root === b.$root;
  /** Gap between stacked toasts, in pixels (Tailwind's gap-2). */
  const GAP = 8;
  /** Open toasts may fill at most this share of the viewport height; later ones wait in the queue. */
  const MAX_STACK_SHARE = 0.4;

  /**
   * The toasts on the page, shared by all `toast` components.
   *
   * Open toasts are kept in opening order and stacked at the bottom of the
   * viewport, the newest lowest. Each toast keeps its own fixed region in
   * the DOM, so out-of-band swaps by `id`, htmx bindings and each toast's
   * live region keep working; only the region's `bottom` changes. A toast
   * that would grow the stack past `MAX_STACK_SHARE` of the viewport waits
   * in the queue, unannounced, until open toasts close. `<html>` gets a
   * `scroll-padding-bottom` as tall as the stack, so a control focused with
   * Tab scrolls above the toasts (WCAG 2.4.11).
   * */
  const stack = {
    open: [],
    queued: [],
    resizeObserver: new ResizeObserver(() => stack.layout()),

    /** Opens the toast now if the stack has room for it, else queues it. */
    request(toast) {
      if (this.height() < MAX_STACK_SHARE * window.innerHeight) {
        this.show(toast);
      } else {
        this.queued.push(toast);
      }
    },
    show(toast) {
      this.open.push(toast);
      toast.isOpen = true;
      this.resizeObserver.observe(toast.$refs.panel);
    },
    /** Removes a closed or dequeued toast, then opens queued toasts while there is room. */
    remove(toast) {
      this.queued = this.queued.filter((t) => !same(t, toast));
      if (!this.open.some((t) => same(t, toast))) {
        return;
      }
      this.open = this.open.filter((t) => !same(t, toast));
      this.resizeObserver.unobserve(toast.$refs.panel);
      toast.$refs.region.style.bottom = '';
      this.layout();
      while (this.queued.length && this.height() < MAX_STACK_SHARE * window.innerHeight) {
        this.show(this.queued.shift());
      }
    },
    /** Total height of the open toasts and the gaps between them. */
    height() {
      return this.open.reduce((sum, t, i) => sum + t.$refs.panel.offsetHeight + (i ? GAP : 0), 0);
    },
    /** Places the newest toast at the region's own bottom offset and each older one above the newer ones. */
    layout() {
      let offset = 0;
      let top = 0;
      for (const toast of [...this.open].reverse()) {
        const region = toast.$refs.region;
        region.style.bottom = '';
        const bottom = parseFloat(getComputedStyle(region).bottom) + offset;
        region.style.bottom = `${bottom}px`;
        top = bottom + toast.$refs.panel.offsetHeight;
        offset += toast.$refs.panel.offsetHeight + GAP;
      }
      document.documentElement.style.scrollPaddingBottom = this.open.length ? `${top}px` : '';
    },
    /** Escape closes the toast that contains focus, else the newest one. */
    onKeydown(event) {
      if (event.key !== 'Escape' || !stack.open.length) {
        return;
      }
      const toast =
        stack.open.find((t) => t.$refs.region.contains(document.activeElement)) ?? stack.open.at(-1);
      toast.close();
    },
  };
  window.addEventListener('keydown', stack.onKeydown);
  window.addEventListener('resize', () => stack.layout());

  /**
   * Status toast for `cotton/toast.html`.
   *
   * Handles opening and closing of a toast; `stack` above places several
   * open toasts. Focus is returned to its trigger when corresponding. AT
   * content announcement is triggered by swapping contents of its
   * `role="status"` live region already present in the document, when the
   * toast is shown rather than while it waits in the queue.
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
          // Measure once the panel has its open styles.
          this.$nextTick(() => stack.layout());
        } else {
          this.$refs.live.replaceChildren();
        }
      });
    },
    /** Opens this toast, or queues it while the stack is full. Opening an open or queued toast again does nothing. */
    open() {
      if (this.isOpen || stack.queued.some((t) => same(t, this))) {
        return;
      }
      this.opener = this.activeElementOrTrigger();
      stack.request(this);
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
    /** Closes this toast and moves focus back to its trigger if it was inside the toast contents. */
    close() {
      const focusWasInside = this.$refs.region.contains(document.activeElement);
      this.isOpen = false;
      stack.remove(this);
      if (focusWasInside && this.opener?.isConnected) {
        this.opener.focus({ preventScroll: true });
      }
      this.opener = null;
    },
    /** Removes a toast that is swapped out of the page, so the stack forgets it. */
    destroy() {
      stack.remove(this);
    },
  }));
});
