document.addEventListener("alpine:init", () => {
  Alpine.data("docketPage", () => ({
    navigateToSelected(event) {
      const url = event.target.value;
      if (url) window.location.href = url;
    },
  }));
});
