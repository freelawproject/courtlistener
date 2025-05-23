function updatePrayerButton(button, lock = false) {
  // Get the document ID.
  let documentId = button.dataset.documentId;
  // Get all the forms on the page with the same documentId
  let prayerForms = document.querySelectorAll(`#pray_${documentId}`);
  let prayerFormsArray = [...prayerForms];
  prayerFormsArray.forEach((form) => {
    let prayerCounterSpan = form.querySelector(`#counter_${documentId}`);
    let prayerButton = form.querySelector('button');

    // Get the current prayer count.
    let prayerCount = parseInt(prayerCounterSpan.innerText, 10);

    // Update the button's class and prayer count based on its current state.
    if (prayerButton.classList.contains('btn-primary')) {
      // If the button is primary (already prayed), change it to default and
      // decrement the count.
      prayerButton.classList.add('btn-default');
      prayerButton.classList.remove('btn-primary');
      prayerCount--;
    } else {
      // If the button is default (not yet prayed), change it to primary and
      // increment the count.
      prayerButton.classList.remove('btn-default');
      prayerButton.classList.add('btn-primary');
      prayerCount++;
    }
    // Update the prayer counter display.
    prayerCounterSpan.innerText = prayerCount;

    if (lock) {
      prayerButton.classList.add('locked');
    } else {
      if (prayerButton.classList.contains('locked')) button.classList.remove('locked');
    }
  });
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
  showTutorialModal();
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
  // To prevent redundant prayer button updates on a single page with multiple
  // prayer buttons, we check if the current element has the "locked" class.
  // This indicates that the prayer button has already been processed in a
  // previous update cycle.
  if (event.detail.fragment.querySelector('#daily_limit_tooltip') && !button.classList.contains('locked')) {
    updatePrayerButton(button, true);
  }
  let documentId = button.dataset.documentId;
  let prayerCounterSpan = document.querySelector(`#counter_${documentId}`);
  let prayerCount = parseInt(prayerCounterSpan.innerText, 10);
  event.detail.fragment.getElementById(`counter_${documentId}`).innerText = prayerCount;
});

document.addEventListener('htmx:oobAfterSwap', function (event) {
  $('[data-toggle="tooltip"]').tooltip();
});

//////////////////////////////////////////////
// Tutorial Modal Cookie Handling (NEW)
//////////////////////////////////////////////
function showTutorialModal() {
  if (!$('#tutorialModal').length) return;
  if (!document.cookie.includes('seen_tutorial=true')) {
    $('#tutorialModal').modal('show');
    let date = new Date();
    date.setTime(date.getTime() + 399 * 24 * 60 * 60 * 1000); // 399 days
    let expires = '; expires=' + date.toGMTString();
    document.cookie = 'seen_tutorial=true' + expires + '; samesite=lax; path=/';
  }
}
