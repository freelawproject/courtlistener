document.addEventListener('DOMContentLoaded', function(){

  const calendarFields = document.querySelector('.date-calendar-fields');
  const relativeFields = document.querySelector('.date-relative-fields');
  const calendarAfter = document.getElementById('id_filed_after');
  const calendarBefore = document.getElementById('id_filed_before');
  const relativeInput = document.getElementById('id_filed_after_relative');
  const relativeBtn = document.querySelector('.btn-dropdown-toggle');
  const relativeList = document.querySelector('.relative-options-list');
  const modeRadios = document.querySelectorAll('input[name="date-mode"]');

  // toggle date filter mode
  function toggleMode() {
    const mode = document.querySelector('input[name="date-mode"]:checked').value;
    const isCalendar = mode === 'calendar';
    // toggle mode forms visibility
    calendarFields.classList.toggle('htmx-hidden-indicator', !isCalendar);
    relativeFields.classList.toggle('htmx-hidden-indicator', isCalendar);
    // To avoid duplicate filed_after parameters in the GET request, remove the name attribute from
    // the field that isn’t in use.
    if (isCalendar) {
      calendarAfter.name = 'filed_after';
      relativeInput.name = '';
    } else {
      calendarAfter.name = '';
      relativeInput.name = 'filed_after';
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
