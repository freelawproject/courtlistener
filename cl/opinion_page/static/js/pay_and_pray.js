function updatePrayerButton(button) {
  // Get the document ID and prayer counter element from the button.
  let documentId = button.dataset.documentId;
  let prayerCounterSpan = document.querySelector(`#counter_${documentId}`);

  // Get the current prayer count.
  let prayerCount = parseInt(prayerCounterSpan.innerText, 10);

  // Update the button's class and prayer count based on its current state.
  if (button.classList.contains('btn-primary')) {
    // If the button is primary (already prayed), change it to default and
    // decrement the count.
    button.classList.add('btn-default');
    button.classList.remove('btn-primary');
    prayerCount--;
  } else {
    // If the button is default (not yet prayed), change it to primary and
    // increment the count.
    button.classList.remove('btn-default');
    button.classList.add('btn-primary');
    prayerCount++;
  }
  // Update the prayer counter display.
  prayerCounterSpan.innerText = prayerCount;
}

document.addEventListener('htmx:beforeRequest', function (event) {
  // Before sending the request, update the button's appearance and counter to
  // provide instant feedback.
  let form = event.detail.elt;
  let button = form.querySelector('button');
  updatePrayerButton(button);
});

document.addEventListener('htmx:afterRequest', function (event) {
  // If the request was successful, don't update the button as it will be
  // updated by another HTMX event.
  if (event.detail.successful) return;

  // If there was an error, revert the changes made to the button and counter.
  let form = event.detail.elt;
  let button = form.querySelector('button');
  updatePrayerButton(button);
});

document.addEventListener('htmx:oobBeforeSwap', function (event) {
  // Before swapping the new content, update the prayer counter in the incoming
  // fragment to avoid unnecessary server calculations.
  let form = event.detail.elt;
  let button = form.querySelector('button');
  // If the daily limit tooltip is present in the fragment, it means the user
  // has reached their limit. Therefore, we should revert any changes made to
  // the prayer button.
  if (event.detail.fragment.querySelector('#daily_limit_tooltip')) {
    updatePrayerButton(button);
  }
  let documentId = button.dataset.documentId;
  let prayerCounterSpan = document.querySelector(`#counter_${documentId}`);
  let prayerCount = parseInt(prayerCounterSpan.innerText, 10);
  event.detail.fragment.getElementById(`counter_${documentId}`).innerText = prayerCount;
});

document.addEventListener('htmx:oobAfterSwap', function (event) {
  $('[data-toggle="tooltip"]').tooltip();
});
