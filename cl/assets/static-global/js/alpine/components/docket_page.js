document.addEventListener("alpine:init", () => {
  Alpine.data("docketPage", () => ({
    navigateToSelected(event) {
      const url = event.target.value;
      if (url) window.location.href = url;
    },
  }));

  // Alpine root for the staff actions row, which only reads the viewCount store.
  Alpine.data("docketStaffActions", () => ({}));
});
