/**
 * Create a calendar that edits a temporary value until Apply is pressed.
 * The visible input remains a normal form control, including for keyboard users.
 */
function createConfirmedDatePicker(hiddenInput, input, { allowFuture = false } = {}) {
  const container = input.parentElement;
  const dialogPanel = input.closest('[x-dialog\\:panel]');
  const stopTemporaryEvent = (event) => event.stopPropagation();
  hiddenInput.addEventListener('input', stopTemporaryEvent);
  hiddenInput.addEventListener('change', stopTemporaryEvent);

  // The mobile dialog traps focus inside its panel, so its calendar must also
  // live there. Flatpickr's default body-relative coordinates are not suitable
  // for that fixed-position panel.
  const positionInDialog = (instance) => {
    const calendar = instance.calendarContainer;
    const bounds = input.getBoundingClientRect();
    const width = calendar.offsetWidth;
    const height = calendar.offsetHeight;
    const top = bounds.bottom + height + 2 <= window.innerHeight
      ? bounds.bottom + 2
      : Math.max(0, bounds.top - height - 2);
    calendar.style.position = 'fixed';
    calendar.style.top = `${top}px`;
    calendar.style.left = `${Math.max(0, Math.min(bounds.left, window.innerWidth - width))}px`;
    calendar.style.right = 'auto';
  };

  let swallowEscape = false;
  const onKeyDown = (event) => {
    if (event.key !== 'Escape' || !picker.isOpen) return;
    event.preventDefault();
    event.stopPropagation();
    swallowEscape = true;
    picker.close();
    input.focus();
  };
  const onKeyUp = (event) => {
    if (event.key !== 'Escape' || !swallowEscape) return;
    swallowEscape = false;
    event.preventDefault();
    event.stopPropagation();
  };
  const open = () => {
    if (!input.disabled) picker.open();
  };
  const closeOnTyping = () => {
    if (picker.isOpen) picker.close();
  };

  const picker = flatpickr(hiddenInput, {
    dateFormat: 'm/d/Y',
    ...(allowFuture ? {} : { enable: [(date) => date <= new Date()] }),
    allowInput: true,
    ariaDateFormat: 'F j, Y',
    locale: { firstDayOfWeek: 1 },
    clickOpens: false,
    closeOnSelect: false,
    disableMobile: true,
    positionElement: input,
    ignoredFocusElements: [container],
    ...(dialogPanel ? { appendTo: dialogPanel, position: positionInDialog } : {}),
    plugins: [confirmDatePlugin({ showAlways: true, confirmText: '', confirmIcon: '' })],
    onOpen: [(_, __, instance) => {
      const value = input.value.trim();
      if (value) instance.setDate(value, false, 'm/d/Y');
      else instance.clear(false);
    }],
    onClose: [(_, __, instance) => {
      const restoreFocus = instance.calendarContainer.contains(document.activeElement);
      instance.clear(false);
      if (restoreFocus) input.focus();
    }],
    onReady: [(_, __, instance) => {
      const confirm = instance.calendarContainer.querySelector('.flatpickr-confirm');
      confirm.innerHTML = `
        <div class="flex gap-3 px-6 w-full pt-4 border-t border-greyscale-200">
          <button type="button" class="btn-outline flex-grow justify-center" data-action="cancel">Cancel</button>
          <button type="button" class="btn-primary flex-grow justify-center" data-action="apply">Apply</button>
        </div>
      `;
      confirm.querySelector('[data-action="apply"]').addEventListener('click', (event) => {
        event.stopPropagation();
        input.value = instance.input.value || '';
        instance.close();
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.focus();
      });
      confirm.querySelector('[data-action="cancel"]').addEventListener('click', (event) => {
        event.stopPropagation();
        instance.close();
        input.focus();
      });
    }],
    onDestroy: [() => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('keyup', onKeyUp, true);
      container.removeEventListener('click', open);
      input.removeEventListener('input', closeOnTyping);
      hiddenInput.removeEventListener('input', stopTemporaryEvent);
      hiddenInput.removeEventListener('change', stopTemporaryEvent);
    }],
  });
  hiddenInput.type = 'hidden';
  container.addEventListener('click', open);
  input.addEventListener('input', closeOnTyping);
  document.addEventListener('keydown', onKeyDown, true);
  document.addEventListener('keyup', onKeyUp, true);
  return picker;
}
