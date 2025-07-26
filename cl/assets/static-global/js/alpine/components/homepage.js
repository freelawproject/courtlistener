const scopeTaglines = [
  { scope: 'o', tagline: 'Search millions of opinions across hundreds of jurisdictions' },
  { scope: 'r', tagline: 'Search our database of millions of PACER documents and dockets' },
  { scope: 'oa', tagline: 'Search the biggest collection of oral argument audio on the Internet' },
  { scope: 'p', tagline: 'Search our database of thousands of State and Federal judges' },
];

document.addEventListener('alpine:init', () => {
  Alpine.data('homepage', () => ({
    ...createFocus(),
    atStart: true,
    atEnd: false,
    get stepWidth() {
      return this.$refs.container.clientWidth * 0.9;
    },
    get tagline() {
      const selected = this.$store.corpusSearch?.selectedScope.type;
      const index = scopeTaglines.findIndex((el) => el.scope === selected);
      if (index === -1) return scopeTaglines[0].tagline;
      return scopeTaglines[index].tagline;
    },
    init() {
      this.updateButtons();
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
