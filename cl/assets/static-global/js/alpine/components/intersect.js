document.addEventListener('alpine:init', () => {
  Alpine.data('intersect', () => ({
    visibleSection: '', // id of the last intersected element
    activeItemClasses: '',
    inactiveItemClasses: '',
    intersectIdAttr: '', // camelCase name of the attribute used to associate $el with target
    show() {
      this.visibleSection = this.$el.id;
    },
    get isVisible() {
      return `#${this.visibleSection}` === this.$el.dataset[this.intersectIdAttr];
    },
    get itemClass() {
      return this.isVisible ? this.activeItemClasses : this.inactiveItemClasses;
    },
    init() {
      this.activeItemClasses = this.$el.dataset?.activeItemClasses;
      this.inactiveItemClasses = this.$el.dataset?.inactiveItemClasses;
      this.intersectIdAttr = this.$el.dataset?.intersectIdAttr;
      this.$nextTick(() => {
        this.visibleSection = this.$el.dataset?.firstActive ?? '';
      });
    },
  }));
});
