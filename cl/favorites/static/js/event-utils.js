document.addEventListener('DOMContentLoaded', async () => {
  const url = '/api/rest/v4/increment-event/';

  // Get the event label element
  const labelElement = document.getElementById('event_label');
  if (!labelElement || !labelElement.value) {
    console.warn('Event label is missing or empty.');
    return;
  }

  const payload = { label: labelElement.value };
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    console.error(' Error when trying to increment count for event ' + labelElement.value);
    return;
  }

  // Update count in the DOM if the element exists
  const countElement = document.getElementById('event_count');
  if (countElement) {
    const data = await response.json();
    countElement.textContent = data.value;
  }
});
