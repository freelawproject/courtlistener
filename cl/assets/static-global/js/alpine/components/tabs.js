function hasUnloadedScripts(page) {
  const loaded = new Set([...document.scripts].map((script) => script.getAttribute('src')));
  return [...page.querySelectorAll('script[src]')].some(
    (script) => !loaded.has(script.getAttribute('src')),
  );
}

document.addEventListener('alpine:init', () => {
  Alpine.data('tabsComponent', () => ({
    isBusy: false,
    errorMessage: "",

    startRequest() {
      this.isBusy = true;
      this.errorMessage = "";
    },
    endRequest() {
      this.isBusy = false;
    },
    handleSendError() {
      this.isBusy = false;
      this.errorMessage = "Couldn't load this tab. Please check your connection and try again.";
    },
    handleResponseError(event) {
      this.isBusy = false;
      const { xhr, pathInfo } = event.detail;

      if (xhr.status >= 500) {
        this.errorMessage = "An error occurred on our end. Please try again.";
        return;
      }
      // Not found, forbidden and similar are full pages; let the browser show them.
      window.location.assign(pathInfo.requestPath);
    },
    handleBeforeSwap(event) {
      if (!event.detail.shouldSwap) return;
      // An expired session answers with the login page, which lacks this component, and a
      // tab's page may need scripts this page never loaded, which a swap can't run. Load
      // either in full instead.
      const page = new DOMParser().parseFromString(event.detail.serverResponse, 'text/html');
      if (page.getElementById(this.$root.id) && !hasUnloadedScripts(page)) return;
      event.detail.shouldSwap = false;
      window.location.assign(event.detail.pathInfo.requestPath);
    },
  }));
});
