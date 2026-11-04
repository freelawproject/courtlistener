document.addEventListener('alpine:init', () => {
  Alpine.data('dismissibleBanner', () => ({
    cookieName: '',
    dismissDays: 0,

    init() {
      this.cookieName = this.$root.dataset.cookieName;
      this.dismissDays = Number(this.$root.dataset.dismissDays);
    },

    close() {
      const date = new Date();
      date.setTime(date.getTime() + this.dismissDays * 24 * 60 * 60 * 1000);
      document.cookie = `${this.cookieName}=1; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
      this.$root.remove();
    }
  }));
});
