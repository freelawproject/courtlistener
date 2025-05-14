/*
API for interacting with clipboard in Alpine's CSP-friendly build,
which doesn't support inline JavaScript.

Usage:

```
{% load component_tags %}
{% require_script "js/alpine/composables/clipboard.js" %}
```

Example:
```
<button
  x-data="copy"
  x-on:click="copyToClipboard"
  data-text-to-copy="This text will be copied when this button is pressed"
>
  Copy text
</button>
```
*/

document.addEventListener('alpine:init', () => {
  Alpine.data('copy', () => ({
    copyToClipboard() {
      const textToCopy = document.createElement('textarea');
      textToCopy.innerHTML = this.$el.dataset?.textToCopy;
      navigator.clipboard.writeText(textToCopy.value.trim());
    },
  }));
});
