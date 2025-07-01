document.addEventListener('alpine:init', () => {
  Alpine.data('homepage', () => ({
    ...createFocus(),
    atStart: true,
    atEnd: false,
    get stepWidth() {
      return this.$refs.container.clientWidth * 0.9;
    },
    init() {
      this.updateButtons();
      this.$refs.container.addEventListener('scroll', () => this.updateButtons());
      window.addEventListener('resize', () => this.updateButtons());
    },
    scrollIntoView() {
      const rect = this.$el.getBoundingClientRect();
      const isPartiallyHidden =
        rect.top < 0 ||
        rect.left < 0 ||
        rect.bottom > window.innerHeight ||
        rect.right > window.innerWidth;
      if (isPartiallyHidden) this.$el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    },
    scrollPrev() {
      this.$refs.container.scrollBy({ left: -this.stepWidth, behavior: 'smooth' });
    },
    scrollNext() {
      this.$refs.container.scrollBy({ left: this.stepWidth, behavior: 'smooth' });
    },
    updateButtons() {
      const c = this.$refs.container;
      this.atStart = c.scrollLeft === 0;
      this.atEnd = c.scrollLeft + c.clientWidth >= c.scrollWidth - 1;
    },
  }));
});
