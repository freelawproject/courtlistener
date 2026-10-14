document.addEventListener('alpine:init', () => {
  Alpine.data('dismissibleBanner', (bannerId, days) => ({
    close() {
      const date = new Date();
      date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
      document.cookie = `banner_dismissed_${bannerId}=1; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
      this.$refs.banner.remove();
    }
  }));
});
