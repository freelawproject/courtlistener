if (typeof window.htmx !== "undefined") {
  htmx.on("htmx:afterSettle", function(detail) {
      if (
          typeof window.djdt !== "undefined"
          && detail.target instanceof HTMLBodyElement
      ) {
          djdt.show_toolbar();
      }
  });
}
