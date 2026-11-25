function positionCalendarInDialog(instance, input) {
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
}

document.addEventListener('alpine:init', () => {
  Alpine.data('confirmedDatePicker', () => {
    const listeners = new AbortController();
    const { signal } = listeners;
    let picker;
    let handledEscape = false;

    return {
      init() {
        const container = this.$el;
        const input = container.querySelector('input[type="text"]');
        const draft = container.querySelector('[data-confirmed-date-picker]');
        const dialog = container.closest('[x-dialog\\:panel]');

        // Flatpickr writes to a separate control until the user clicks Apply.
        for (const type of ['input', 'change']) {
          draft.addEventListener(type, (event) => event.stopPropagation(), { signal });
        }
        picker = flatpickr(draft, {
          dateFormat: 'm/d/Y',
          ...('allowFutureDates' in container.dataset ? {} : { enable: [(date) => date <= new Date()] }),
          allowInput: true,
          ariaDateFormat: 'F j, Y',
          locale: { firstDayOfWeek: 1 },
          clickOpens: false,
          closeOnSelect: false,
          disableMobile: true,
          positionElement: input,
          ignoredFocusElements: [container],
          // Keep the calendar inside the mobile dialog's focus trap.
          ...(dialog ? {
            appendTo: dialog,
            position: (instance) => positionCalendarInDialog(instance, input),
          } : {}),
          onOpen: (_, __, instance) => instance.setDate(input.value.trim()),
          onClose: (_, __, instance) => {
            const restoreFocus = instance.calendarContainer.contains(document.activeElement);
            instance.clear(false);
            if (restoreFocus) input.focus();
          },
          onReady: (_, __, instance) => {
            const actions = document.createElement('div');
            actions.className = 'flex gap-3 px-6 w-full pt-4 border-t border-greyscale-200';
            actions.innerHTML = `
              <button type="button" class="btn-outline flex-grow justify-center" data-action="cancel">Cancel</button>
              <button type="button" class="btn-primary flex-grow justify-center" data-action="apply">Apply</button>
            `;
            actions.addEventListener('click', (event) => {
              const button = event.target.closest('button');
              if (!button) return;
              event.stopPropagation();
              const apply = button.dataset.action === 'apply';
              if (apply) input.value = draft.value;
              instance.close();
              if (apply) {
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
              }
              input.focus();
            }, { signal });
            instance.calendarContainer.append(actions);
          },
        });

        // Flatpickr normalizes its target to a text input during setup.
        draft.type = 'hidden';
        container.addEventListener('click', () => {
          if (!input.disabled) picker.open();
        }, { signal });
        input.addEventListener('input', () => {
          if (picker.isOpen) picker.close();
        }, { signal });
        document.addEventListener('keydown', (event) => {
          if (event.key !== 'Escape' || !picker.isOpen) return;
          event.preventDefault();
          event.stopPropagation();
          handledEscape = true;
          picker.close();
          input.focus();
        }, { capture: true, signal });
        document.addEventListener('keyup', (event) => {
          if (event.key !== 'Escape' || !handledEscape) return;
          handledEscape = false;
          event.preventDefault();
          event.stopPropagation();
        }, { capture: true, signal });
      },
      destroy() {
        listeners.abort();
        picker.destroy();
      },
    };
  });
});
