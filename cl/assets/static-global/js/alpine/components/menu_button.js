document.addEventListener('alpine:init', () => {
  Alpine.data('menuButton', () => ({
    get itemClass() {
      if (this.$menuItem.isActive) {
        return this.$el.dataset.itemClass + ' ' + this.$el.dataset.focusedClass;
      }
      return this.$el.dataset.itemClass;
    },
    openDialog(event) {
      // Close the menu first so focus returns to the trigger before the
      // dialog traps it; on dialog close, focus then lands on a visible element.
      const dialogName = event.currentTarget.dataset.dialog;
      this.$data.__close();
      this.$nextTick(() => this.$dispatch(dialogName));
    },
  }));
});
