/*
Detects the RECAP extension and records it for the stylesheet and the server.
The extension announces itself with a window message on every page load. On
that message, `<html>` gets the `recap-installed` class, which hides every
`[data-recap-plea]` element, and the `recap_installed` cookie is set so later
responses render the class themselves and can read the signal server-side.
Loaded by `new_base.html` on every page; templates never require it. Usage
and caveats: FRONTEND.md, "RECAP extension".
*/

const RECAP_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

// Registered at load rather than on alpine:init: the extension's content
// script may post before Alpine starts, and a later listener would miss it.
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
