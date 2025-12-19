/**
 * Disclosure typeahead behavior
 * - Click outside closes the dropdown
 * - Escape key closes dropdown and clears input
 * - Trim whitespace before sending requests
 */
document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("id_disclosures_search");
  const results = document.getElementById("disclosure-search-results");

  if (!input || !results) return;

  // Close dropdown when clicking outside
  document.addEventListener("click", function (e) {
    const searchContainer = document.querySelector(".search-input-judges");
    if (searchContainer && !searchContainer.contains(e.target)) {
      results.innerHTML = "";
    }
  });

  // Escape key: close dropdown and clear input
  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      results.innerHTML = "";
      input.value = "";
      input.blur();
    }
  });

  // Cancel HTMX request if trimmed query is too short
  input.addEventListener("htmx:beforeRequest", function (e) {
    const trimmed = input.value.trim();
    if (trimmed.length < 2) {
      e.preventDefault();
      results.innerHTML = "";
    }
  });
});
