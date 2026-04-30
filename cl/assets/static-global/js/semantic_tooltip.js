document.addEventListener('DOMContentLoaded', function () {
  const tooltip = document.getElementById('semantic-tooltip');
  const closeBtn = document.getElementById('semantic-tooltip-close');
  const toggle = document.querySelector('.search-mode-toggle');

  if (!tooltip || !closeBtn || !toggle) return;
  if (localStorage.getItem('semanticTooltipDismissed')) return;

  const toggleRect = toggle.getBoundingClientRect();
  const parentRect = toggle.closest('.input-group').getBoundingClientRect();

  tooltip.style.top = toggleRect.height + 'px';
  tooltip.style.left = (toggleRect.left - parentRect.left) + 'px';
  tooltip.style.display = 'block';

  closeBtn.addEventListener('click', function (event) {
    tooltip.style.display = 'none';
    localStorage.setItem('semanticTooltipDismissed', 'true');
    event.preventDefault();
  });
});
