/**
 * Disclosure typeahead behavior
 * - Click outside closes the dropdown
 * - Escape key closes dropdown and clears input
 * - Arrow keys navigate through results
 * - Enter key activates selected result
 * - Trim whitespace before sending requests
 */
document.addEventListener('DOMContentLoaded', function () {
  const input = document.getElementById('id_disclosures_search');
  const results = document.getElementById('disclosure-search-results');

  if (!input || !results) return;

  let selectedIndex = -1;

  function getResultLinks() {
    return results.querySelectorAll('.disclosure-result-link');
  }

  function updateSelection(links) {
    links.forEach((link, i) => {
      const row = link.closest('.tr-results');
      if (i === selectedIndex) {
        row.classList.add('active');
      } else {
        row.classList.remove('active');
      }
    });
  }

  function resetSelection() {
    selectedIndex = -1;
    const links = getResultLinks();
    links.forEach((link) => {
      link.closest('.tr-results').classList.remove('active');
    });
  }

  // Close dropdown when clicking outside
  document.addEventListener('click', function (e) {
    const searchContainer = document.querySelector('.search-input-judges');
    if (searchContainer && !searchContainer.contains(e.target)) {
      results.innerHTML = '';
      resetSelection();
    }
  });

  // Keyboard navigation
  input.addEventListener('keydown', function (e) {
    const links = getResultLinks();

    if (e.key === 'Escape') {
      results.innerHTML = '';
      input.value = '';
      input.blur();
      resetSelection();
      return;
    }

    if (links.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, links.length - 1);
      updateSelection(links);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
      updateSelection(links);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      links[selectedIndex].click();
    }
  });

  // Reset selection when new results arrive
  results.addEventListener('htmx:afterSwap', function () {
    resetSelection();
  });

  // Cancel HTMX request if trimmed query is too short
  input.addEventListener('htmx:beforeRequest', function (e) {
    const trimmed = input.value.trim();
    if (trimmed.length < 2) {
      e.preventDefault();
      results.innerHTML = '';
      resetSelection();
    }
  });
});
