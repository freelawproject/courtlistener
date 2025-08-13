document.addEventListener('DOMContentLoaded', function () {
  const copyBtn = document.getElementById('copyBtn');
  const defaultIcon = document.getElementById('defaultIcon');
  const successIcon = document.getElementById('successIcon');
  const input = document.getElementById('user_id');

  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(input.value);
      showSuccess();
      setTimeout(resetToDefault, 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  });

  function showSuccess() {
    defaultIcon.classList.add('hidden');
    successIcon.classList.add('flex');
    successIcon.classList.remove('hidden');
  }

  function resetToDefault() {
    defaultIcon.classList.remove('hidden');
    successIcon.classList.add('hidden');
  }
});
