/*
Alpine directive `x-busy-button` for the wrapper around a busy-capable
`<c-button>`. The caller toggles `aria-busy` on the button; while busy, this
sets `aria-disabled`, cancels any activation and announces the status
region's `data-busy-text`. It is a directive rather than a component so it
adds no Alpine scope: handlers on the button keep their own `$root`.
*/

document.addEventListener('alpine:init', () => {
  // Wrappers outside any x-data tree, such as the catalog demos, still initialize.
  Alpine.addInitSelector(() => '[x-busy-button]');
  Alpine.directive('busy-button', (wrapper, _directive, { cleanup }) => {
    const button = wrapper.querySelector(':scope > :is(a, button)');
    const status = wrapper.querySelector(':scope > [role="status"]');
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
    /** Cancels activation while busy, before the caller's own click handlers run. */
    const guard = (event) => {
      if (!isBusy()) return;
      event.preventDefault();
      event.stopPropagation();
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(button, { attributes: true, attributeFilter: ['aria-busy'] });
    wrapper.addEventListener('click', guard, true);
    cleanup(() => {
      observer.disconnect();
      wrapper.removeEventListener('click', guard, true);
    });
  });
});
