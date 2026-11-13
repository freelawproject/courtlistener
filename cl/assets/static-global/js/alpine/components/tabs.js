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
    activeTab: "",

    init() {
      this.activeTab = this.$el.dataset.activeTab ?? "";
    },
    get isSelected() {
      return this.$el.dataset.tabKey === this.activeTab;
    },
    get tabIndex() {
      return this.isSelected ? 0 : -1;
    },
    get isInactive() {
      return !this.isSelected;
    },
    selectTab() {
      const key = this.$el.dataset.tabKey;
      if (key === this.activeTab) return;
      this.activeTab = key;
      const url = new URL(window.location.href);
      url.searchParams.set('tab', key);
      history.replaceState(history.state, '', url);
    },
    startRequest() {
      this.isBusy = true;
      this.errorMessage = "";
    },
    endRequest() {
      this.isBusy = false;
    },
    navigateToTab(event) {
      document.getElementById(`${this.$root.id}-tab-${event.target.value}`).click();
    },
    restoreSelectedTab() {
      // The dropdown already shows the tab the user picked, but the request failed and
      // the page still shows the previous one.
      const select = document.getElementById(`${this.$root.id}-select`);
      for (const option of select.options) option.selected = option.defaultSelected;
    },
    handleSendError() {
      this.errorMessage = "Couldn't load this tab. Please check your connection and try again.";
      this.restoreSelectedTab();
    },
    handleResponseError(event) {
      const { xhr, pathInfo } = event.detail;

      if (xhr.status >= 500) {
        this.errorMessage = "An error occurred on our end. Please try again.";
        this.restoreSelectedTab();
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
