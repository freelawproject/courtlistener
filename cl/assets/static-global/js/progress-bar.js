let trickleInterval = null;

function updateProgressBar() {
  let progressElement = document.getElementById('progress-bar');
  let oldValue = 0;
  if ('value' in progressElement.dataset) {
    oldValue = parseFloat(progressElement.dataset.value);
  }
  let newValue = oldValue + Math.random() / 10;
  progressElement.style.width = `${10 + newValue * 85}%`;
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

document.onvisibilitychange = () => {
  if (document.visibilityState !== 'hidden') return;

  let progressElement = document.getElementById('progress-bar');
  if (progressElement == null) return;

  window.clearInterval(trickleInterval);
  progressElement.style.width = '100%';
  progressElement.style.opacity = 0;

  setTimeout(() => {
    let progressElement = document.getElementById('progress-bar');
    progressElement.remove();
  }, 450);
};
