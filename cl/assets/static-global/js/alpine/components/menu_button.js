document.addEventListener('alpine:init', () => {
  Alpine.data('menuButton', () => ({
    get itemClass() {
      if (this.$menuItem.isActive) {
        return this.$el.dataset.itemClass + ' ' + this.$el.dataset.focusedClass;
      }
      return this.$el.dataset.itemClass;
    },
    /**
     * Closes the menu and focuses its trigger synchronously.
     * The plugin's `__close` focuses the trigger on the next tick, too late
     * when a focus trap (e.g. a dialog) may activate before then.
     */
    closeAndFocusTrigger() {
      this.$data.__close(false);
      this.$refs.__button.focus();
    },
  }));
});
