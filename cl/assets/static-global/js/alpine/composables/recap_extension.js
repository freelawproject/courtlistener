/*
Detects the RECAP extension from the message it posts on every page load, and
records it as the `recap-installed` class on <html> and the `recap_installed`
cookie. Loaded by `new_base.html` on every page; templates never require it.
Usage and caveats: FRONTEND.md, "RECAP extension".
*/

const RECAP_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

// Registered at load rather than on alpine:init: the listener needs nothing
// from Alpine, and the order between Alpine's deferred start and the
// extension's content script is not guaranteed.
window.addEventListener('message', (event) => {
  const isRecap =
    event.source === window &&
    event.data?.sender === 'recap-extension' &&
    event.data?.message_name === 'version';
  if (!isRecap) return;
  document.documentElement.classList.add('recap-installed');
  const secure = location.protocol === 'https:' ? '; secure' : '';
  document.cookie = `recap_installed=true; max-age=${RECAP_COOKIE_MAX_AGE_SECONDS}; samesite=lax; path=/${secure}`;
});
