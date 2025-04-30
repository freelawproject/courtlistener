/*
To use this component, add this to your template right after `{% extends "new_base.html" %}`

{% load component_tags %}
{% require_script "js/alpine/components/focus.js" %}
{% require_script "js/alpine/plugins/focus@3.14.8" defer=True %}

Note we need to also register the Alpine plugin focus for this to work.
*/

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
