let trickleInterval = null;

function updateProgressBar() {
  let progressElement = document.getElementById('progress-bar');
  let oldValue = 0;
  if ('value' in progressElement.dataset) {
    oldValue = parseFloat(progressElement.dataset.value);
  }
  let newValue = oldValue + Math.random() / 10;
  if (newValue >= 1) newValue = 1;
  progressElement.style.width = `${10 + newValue * 75}%`;
  progressElement.dataset.value = newValue;
}

function installProgressBar() {
  let progressElement = document.createElement('div');
  progressElement.id = 'progress-bar';
  progressElement.classList.add('turbo-progress-bar');
  progressElement.style.width = '0';
  progressElement.style.opacity = '1';
  document.body.prepend(progressElement);
  trickleInterval = window.setInterval(updateProgressBar, 300);
}

function disableAllSubmitButtons() {
  // Get all submit buttons on the page
  const submitButtons = document.querySelectorAll('input[type="submit"],button[type="submit"]');
  // Disable each element
  submitButtons.forEach((button) => {
    button.disabled = true;
  });
}
