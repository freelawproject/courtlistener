document.addEventListener('alpine:init', () => {
  Alpine.data('menuButton', () => ({
    get itemClass() {
      if (this.$menuItem.isActive) {
        return this.$el.dataset.itemClass + ' ' + this.$el.dataset.focusedClass;
      }
      return this.$el.dataset.itemClass;
    },
  }));
});
