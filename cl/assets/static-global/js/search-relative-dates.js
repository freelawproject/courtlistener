document.addEventListener('DOMContentLoaded', function(){
  const dateFilterWidgets = document.querySelectorAll('.date-filter-mode');

  dateFilterWidgets.forEach((widget) => {
    const fieldPrefix = widget.dataset.fieldPrefix;

    const calendarFields = widget.querySelector('.date-calendar-fields');
    const relativeFields = widget.querySelector('.date-relative-fields');
    const calendarAfter = widget.querySelector('#id_' + fieldPrefix + '_after');
    const calendarBefore = widget.querySelector('#id_' + fieldPrefix + '_before');
    const relativeInput = widget.querySelector('#id_' + fieldPrefix + '_after_relative');
    const relativeBtn = widget.querySelector('.btn-dropdown-toggle');
    const relativeList = widget.querySelector('.relative-options-list');
    const modeRadios = widget.querySelectorAll(`input[name="${fieldPrefix}-date-mode"]`);

    // toggle date filter mode
    function toggleMode() {
      const checkedRadio = widget.querySelector('input[name="' + fieldPrefix + '-date-mode"]:checked');
      if (!checkedRadio) return;
      const mode = checkedRadio.value;
      const isCalendar = mode === 'calendar';
      // toggle mode forms visibility
      calendarFields.classList.toggle('hidden', !isCalendar);
      relativeFields.classList.toggle('hidden', isCalendar);

      // To avoid duplicate filed_after parameters in the GET request, remove the name attribute from
      // the field that isn’t in use.
      if (isCalendar) {
        calendarAfter.name = fieldPrefix + '_after';
        relativeInput.name = '';
      } else {
        calendarAfter.name = '';
        relativeInput.name = fieldPrefix + '_after';
        // In relative mode, also clear the filed_before value to prevent unintended absolute and relative range combinations
        calendarBefore.value = '';
      }

      calendarAfter.disabled = !isCalendar;
      calendarBefore.disabled = !isCalendar;
      relativeInput.disabled = isCalendar;
      relativeBtn.disabled = isCalendar;
      relativeList.classList.remove('show');
    }

    modeRadios.forEach((r) => r.addEventListener('change', toggleMode));
    toggleMode();

    // dropdown toggle
    relativeBtn.addEventListener('click', function(e){
      e.preventDefault();
      relativeList.classList.toggle('show');
    });

    // option click
    relativeList.querySelectorAll('li').forEach((li) => {
      li.addEventListener('click', function () {
        relativeInput.value = this.dataset.value;
        relativeList.classList.remove('show');
      });
    });

    // close when clicking outside
    document.addEventListener('click', function (e) {
      if (!relativeFields.contains(e.target)) {
        relativeList.classList.remove('show');
      }
    });
  });
});
