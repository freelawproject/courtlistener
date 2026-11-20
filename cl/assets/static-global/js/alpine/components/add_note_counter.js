/**
 * Character counter for the note dialog's Notes field.
 *
 * Reads the limit from the textarea's maxlength, so the number lives only in
 * the form widget. The visible count is also the textarea's description, read
 * on focus and on demand. Announces when the remaining count drops to
 * START_ANNOUNCE_AT or reaches zero, instead of on every keystroke.
 */
document.addEventListener("alpine:init", () => {
  const START_ANNOUNCE_AT = 50;

  Alpine.data("noteCounter", () => ({
    remaining: 0,
    announcement: "",
    bandzone: null,

    init() {
      this.textarea = this.$el.querySelector("textarea");
      this.describeTextarea();
      this.update();
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

    update() {
      this.remaining = this.textarea.maxLength - this.textarea.value.length;

      /* Announce when entering a band, not while staying in it, so typing
        within the last 50 characters is silent. Leaving every band clears
        the message so the same text can be announced again later. */
      const bandzone =
        this.remaining <= 0 ? "limit" : this.remaining <= START_ANNOUNCE_AT ? "low" : null;

      if (bandzone === this.bandzone) return;

      this.bandzone = bandzone;
      this.announcement = bandzone ? this.remainingText : "";
    },

    get remainingText() {
      return `${this.remaining} characters remaining.`;
    },
  }));
});
