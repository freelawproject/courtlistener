/*
API for the intersect plugin in Alpine's CSP-friendly build,
which doesn't support inline JavaScript.

Usage:

```
{% load component_tags %}
{% require_script "js/alpine/composables/focus.js" %}
{% require_script "js/alpine/plugins/focus@3.14.8" defer=True %}
```
*/

const createFocus = () => ({
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
  /** Checks if an element with the id provided exists, and if it does, moves focus to it */
  moveFocus(id) {
    const el = document.getElementById(id);
    if (!el) return;
    this.$focus.focus(el);
  },
});

document.addEventListener('alpine:init', () => {
  Alpine.data('focus', createFocus);
});
