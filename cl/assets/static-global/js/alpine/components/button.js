/*
Alpine component behind `<c-button.busy>`. The caller toggles `aria-busy` on
the button; while busy, this sets `aria-disabled`, cancels any activation and
announces the status region's `data-busy-text`. It defines only `init` and
`guard`: the button's own bindings resolve through this scope, so any other
name here would shadow the caller's.
*/

document.addEventListener('alpine:init', () => {
  Alpine.data('busyButton', () => {
    let button;
    let status;
    let disabledByBusy = false;
    const isBusy = () => button.getAttribute('aria-busy') === 'true';
    const sync = () => {
      const busy = isBusy();
      if (busy && !button.hasAttribute('aria-disabled')) {
        button.setAttribute('aria-disabled', 'true');
        disabledByBusy = true;
      } else if (!busy && disabledByBusy) {
        button.removeAttribute('aria-disabled');
        disabledByBusy = false;
      }
      status.textContent = busy ? status.dataset.busyText : '';
    };
    return {
      init() {
        button = this.$root.querySelector(':scope > :is(a, button)');
        status = this.$root.querySelector('[role="status"]');
        sync();
        new MutationObserver(sync).observe(button, { attributes: true, attributeFilter: ['aria-busy'] });
      },
      /** Cancels activation while busy, before the caller's own click handlers run. */
      guard(event) {
        if (!isBusy()) return;
        event.preventDefault();
        event.stopPropagation();
      },
    };
  });
});
