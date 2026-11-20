/**
 * Screen reader confirmation for the note dialog.
 *
 * The dialog closes when a note is saved or deleted, so nothing inside it can
 * speak the result. This fills a status region that stays on the page, from
 * the events the note views send.
 */
document.addEventListener("alpine:init", () => {
  const CLEAR_AFTER_MS = 5000;

  Alpine.data("noteStatus", () => ({
    message: "",

    saved() {
      this.announcesAction(this.$el.dataset.saved);
    },

    deleted() {
      this.announcesAction(this.$el.dataset.deleted);
    },

    announcesAction(text) {
      this.message = text;
      // A live region only speaks when its text changes, so clear it to let
      // the same message be announced again later.
      setTimeout(() => {
        this.message = "";
      }, CLEAR_AFTER_MS);
    },
  }));
});
