/*
Shared flatpickr calendar for every date input in the v2 design, so they all
open, close and look the same: the calendar opens from the calendar icon or a
click on the input, and closes on Esc, on a click outside, when the user types,
and from its Cancel and Apply buttons.

Mark each date input's wrapper with `data-date-input`; the wrapper holds the
text input and, optionally, the calendar icon button. Clicking anywhere in the
wrapper opens the calendar, and typing in the input closes it.

Usage:

```
{% load component_tags %}
{% require_script "js/third_party/flatpickr/flatpickr" %}
{% require_script "js/third_party/flatpickr/plugins/confirmDate" %}
{% require_script "js/alpine/composables/date_picker.js" %}
```

```
Alpine.data('myComponent', () => ({
  ...createDatePicker(),
  init() {
    this.$nextTick(() => this.initDatePickers(this.$el));
  },
}));
```

```
<div data-date-input x-on:click="openDatePicker" x-on:input="closeDatePicker">
  <input type="text">
</div>
```
*/

/** Flatpickr instances by the text input they open next to. Kept out of Alpine's reactive state. */
const datePickerInstances = new WeakMap();

/** Finds the text input of the `data-date-input` wrapper that holds `el`. */
const dateInputOf = (el) => el.closest('[data-date-input]')?.querySelector('input');

/**
 * Binds a calendar to a text input. Flatpickr runs on a hidden proxy input,
 * so it never rewrites what the user typed, and it is positioned next to the
 * real input. The calendar only writes to the real input through Apply.
 */
const bindDatePicker = (input) => {
  const proxy = document.createElement('input');
  proxy.type = 'hidden';
  // Beside the wrapper, not in it: flatpickr fires `input` events on its element, which would reach the wrapper's `input` handler.
  input.closest('[data-date-input]').after(proxy);

  /** Closes the calendar and returns focus to the input, for dismissals made from the calendar itself. */
  const dismiss = (instance) => {
    instance.close();
    input.focus();
  };

  const onOutsidePointerDown = (event) => {
    const path = event.composedPath();
    // Flatpickr re-renders its days on click, so the target can be detached by the time we check; the path is not.
    if (path.includes(instance.calendarContainer) || path.includes(input.closest('[data-date-input]'))) return;
    instance.close();
  };

  /** Esc closes the calendar before anything else, such as a dialog, reacts to it. */
  const onEscape = (event) => {
    if (event.key !== 'Escape' || !instance.isOpen) return;
    event.stopPropagation();
    dismiss(instance);
  };

  const instance = flatpickr(proxy, {
    dateFormat: 'm/d/Y',
    enable: [(date) => date <= new Date()],
    allowInput: true,
    ariaDateFormat: 'F j, Y',
    locale: { firstDayOfWeek: 1 },
    clickOpens: false,
    closeOnSelect: false,
    disableMobile: true,
    positionElement: input,
    // Focusing or clicking the input must not count as leaving the calendar.
    ignoredFocusElements: [input.closest('[data-date-input]')],
    plugins: [confirmDatePlugin({ showAlways: true, confirmText: '', confirmIcon: '' })],
    onReady: [
      (selectedDates, dateStr, instance) => {
        patchConfirm(instance, input, dismiss);
        // Capturing, so it runs before flatpickr's own Esc handling closes the calendar and focus is lost.
        instance.calendarContainer.addEventListener('keydown', onEscape, true);
      },
    ],
    onOpen: [
      () => {
        // Start from whatever the user has typed, if it is a date.
        const typed = input.value.trim();
        if (typed) instance.setDate(typed, true, 'm/d/Y');
        document.addEventListener('pointerdown', onOutsidePointerDown);
      },
    ],
    onClose: [
      () => {
        document.removeEventListener('pointerdown', onOutsidePointerDown);
        instance.clear();
      },
    ],
  });
  // On the wrapper rather than the input, so it also catches Esc while the calendar icon has focus.
  // Flatpickr turns its element into a text input; keep it out of the page and out of the form's fields.
  proxy.type = 'hidden';
  input.closest('[data-date-input]').addEventListener('keydown', onEscape);
  datePickerInstances.set(input, instance);
};

/** Replaces the confirm plugin's single button with the Cancel/Apply pair from the design. */
const patchConfirm = (instance, input, dismiss) => {
  const confirmEl = instance.calendarContainer.querySelector('.flatpickr-confirm');
  if (!confirmEl || confirmEl.dataset.patched) return;

  confirmEl.innerHTML = `
    <div class="flex gap-3 px-6 w-full pt-4 border-t border-greyscale-200">
      <button type="button" class="btn-outline flex-grow justify-center" data-action="cancel">Cancel</button>
      <button type="button" class="btn-primary flex-grow justify-center" data-action="apply">Apply</button>
    </div>
  `;
  confirmEl.dataset.patched = 'true';

  confirmEl.querySelector('[data-action="apply"]').addEventListener('click', () => {
    input.value = instance.input.value || '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    dismiss(instance);
  });
  confirmEl.querySelector('[data-action="cancel"]').addEventListener('click', (e) => {
    e.preventDefault();
    dismiss(instance);
  });
};

const createDatePicker = () => ({
  /** Binds a calendar to every `data-date-input` text input inside `root`. */
  initDatePickers(root) {
    for (const wrapper of root.querySelectorAll('[data-date-input]')) {
      const input = wrapper.querySelector('input');
      if (input && !datePickerInstances.has(input)) bindDatePicker(input);
    }
  },
  /** Opens the calendar of the `data-date-input` wrapper containing the current element. */
  openDatePicker() {
    const input = dateInputOf(this.$el);
    if (!input) return;
    datePickerInstances.get(input)?.open();
    // A click on the icon would otherwise leave focus on the icon, outside the input the calendar belongs to.
    input.focus();
  },
  /** Closes the calendar of the `data-date-input` wrapper containing the current element. */
  closeDatePicker() {
    const input = dateInputOf(this.$el);
    if (input) datePickerInstances.get(input)?.close();
  },
});
