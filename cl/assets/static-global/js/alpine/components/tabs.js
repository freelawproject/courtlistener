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
  }));
});
