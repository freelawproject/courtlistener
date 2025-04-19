document.addEventListener('alpine:init', () => {
  Alpine.data('focus', () => ({
    focusPrevious() {
      this.$focus.wrap().previous();
    },
    focusNext() {
      this.$focus.wrap().next();
    },
    focusFirst() {
      this.$focus.wrap().first();
    },
    focusLast() {
      this.$focus.wrap().last();
    },
  }));
});
