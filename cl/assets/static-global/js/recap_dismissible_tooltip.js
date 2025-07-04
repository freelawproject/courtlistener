document.addEventListener('DOMContentLoaded', function () {
  const tooltip = document.getElementById('recap-tooltip');
  const closeBtn = document.getElementById('tooltip-close-btn');
  const searchBar = document.getElementById('id_q');
  const searchButton = document.getElementById('search-button');

  if (!localStorage.getItem('recapTooltipDismissed')) {
    // Position tooltip
    const searchBarRect = searchBar.getBoundingClientRect();
    const searchButtonRect = searchButton.getBoundingClientRect();
    tooltip.style.top = `${searchBarRect.height}px`;
    tooltip.style.left = `${searchBarRect.width - searchButtonRect.width}px`; // adjust as needed
    tooltip.style.display = 'block';
  }

  closeBtn.addEventListener('click', (event) => {
    tooltip.style.display = 'none';
    localStorage.setItem('recapTooltipDismissed', 'true');
    event.preventDefault();
  });
});
