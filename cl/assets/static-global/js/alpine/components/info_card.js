document.addEventListener('alpine:init', () => {
  Alpine.data('dismissibleCard', (cardId, days) => ({
    close() {
      const date = new Date();
      date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
      document.cookie = `card_dismissed_${cardId}=1; expires=${date.toUTCString()}; path=/; SameSite=Lax`;
      this.$refs.card.remove();
    }
  }));
});
