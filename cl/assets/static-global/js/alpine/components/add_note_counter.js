/**
 * Character counter for the note dialog's Notes field.
 *
 * Reads the limit from the textarea's maxlength, so the number lives only in
 * the form widget. The visible count is also the textarea's description, read
 * on focus and on demand. Within the last START_ANNOUNCE_AT characters, the
 * remaining count is announced each time the user pauses typing, never on a
 * keystroke.
 */
document.addEventListener("alpine:init", () => {
  const START_ANNOUNCE_AT = 50;
  const PAUSE_MS = 1000;

  Alpine.data("noteCounter", () => ({
    remaining: 0,
    announcement: "",
    announceTimer: null,

    init() {
      this.textarea = this.$el.querySelector("textarea");
      this.describeTextarea();
      this.remaining = this.countRemaining();
    },

    // Link the visible count from the textarea's aria-describedby. Any
    // existing id, such as the field's error message, stays first.
    describeTextarea() {
      const count = this.$refs.count;
      count.id = `${this.textarea.id}-count`;
      const ids = (this.textarea.getAttribute("aria-describedby") || "")
        .split(" ")
        .filter(Boolean);
      if (!ids.includes(count.id)) ids.push(count.id);
      this.textarea.setAttribute("aria-describedby", ids.join(" "));
    },

    // Each keystroke empties the status region and restarts the timer, so
    // nothing is spoken while typing. A pause puts the count back, which is
    // always a change, so the same count can be announced again.
    update() {
      this.remaining = this.countRemaining();
      clearTimeout(this.announceTimer);
      this.announcement = "";
      if (this.remaining > START_ANNOUNCE_AT) return;

      this.announceTimer = setTimeout(() => {
        this.announcement = this.remainingText;
      }, PAUSE_MS);
    },

    countRemaining() {
      return this.textarea.maxLength - this.textarea.value.length;
    },

    get remainingText() {
      return `${this.remaining} characters remaining.`;
    },
  }));
});
