// Webhooks htmx event handlers
htmx.on('htmx:beforeSend', (e) => {
  let target_trigger = e.detail.requestConfig.headers['HX-Trigger'];
  if (
    e.detail.target.id === 'webhook_table_body' &&
    (target_trigger === 'webhook-filter-form' || target_trigger === 'webhooks-paginator')
  ) {
    //Show the loader spinner when sending the webhook filter or paginator request
    $('#webhook_list_loader').removeClass('hidden');
    $('#webhook_table_body').addClass('hidden');
  }
  if (e.detail.target.id === 'webhook_table_body' && target_trigger === 'webhooks-paginator' && !e.detail.isError) {
    //Scroll toward the results before the pagination request.
    document.getElementById('webhook-filter-form').scrollIntoView();
  }
});

htmx.on('htmx:afterSwap', (e) => {
  //Load the form over the modal
  let webhook_form = document.getElementById('webhooks-body');
  if (e.detail.target.id === 'webhooks-body') {
    // If the user already have a webhook configured for each type of event, show a message.
    let event_type_options = document.getElementById('id_event_type').options.length;
    if (event_type_options === 0) {
      webhook_form.innerHTML =
        "<b class='text-center'>You already have a webhook configured for each type of event. Please delete one before making another.</b>";
    }
    //Toggle form modal
    $('#webhook-modal').modal('toggle');
  }

  if (e.detail.target.id === 'webhooks-body-testing') {
    //Toggle the webhook testing modal.
    $('#webhook-modal').modal('toggle');
  }

  if (e.detail.target.id === 'webhook-test-sent') {
    // Show the button checkbox square after send the webhook test request.
    $('#webhook-test-sent').removeClass('hidden');
  }

  let target_trigger = e.detail.requestConfig.headers['HX-Trigger'];
  if (
    e.detail.target.id === 'webhook_table_body' &&
    (target_trigger === 'webhook-filter-form' || target_trigger === 'webhooks-paginator') &&
    !e.detail.isError
  ) {
    //Hide the loader spinner and show the table after loading the filter results.
    $('#webhook_list_loader').addClass('hidden');
    $('#webhook_table_body').removeClass('hidden');
  }
});

htmx.on('htmx:beforeSwap', (e) => {
  /*
  After submitting the POST request, toggle the modal back to hidden.
  */
  if (e.detail.target.id === 'webhook-form' && !e.detail.xhr.response) {
    $('#webhook-modal').modal('toggle');

    $('#webhook_table_body').addClass('hidden');
    $('#webhook_list_loader').removeClass('hidden');

    e.detail.shouldSwap = false;
  }

  let webhook_title = document.querySelector('#webhook-modal .modal-title');
  let webhook_form = document.getElementById('webhooks-body');
  let webhook_form_testing = document.getElementById('webhooks-body-testing');
  let target_trigger = e.detail.requestConfig.headers['HX-Trigger'];
  if (e.detail.target.id === 'webhooks-body') {
    // Clean and set the right title according to the HTMX request.
    webhook_form.innerHTML = '';
    webhook_form_testing.innerHTML = '';
    if (target_trigger === 'add-webhook') {
      webhook_title.innerHTML = 'Add webhook endpoint';
    } else {
      webhook_title.innerHTML = 'Edit webhook endpoint';
    }
  }
  if (e.detail.target.id === 'webhooks-body-testing') {
    // Clean and set the right title according to the HTMX request.
    webhook_form.innerHTML = '';
    webhook_form_testing.innerHTML = '';
    webhook_title.innerHTML = 'Test a webhook event';
  }

  /*
  Make sure the loader inside the table is hidden to load new data.
  */
  if (e.detail.target.id === 'webhook_table_body' && !e.detail.isError) {
    $('#webhook_list_loader').addClass('hidden');
    $('#webhook_table_body').removeClass('hidden');
  }

  /*
  After submitting the DELETE request, handle the response to show
  the spinner inside the table or an alert if the request failed
  */
  if (e.detail.requestConfig.verb === 'delete' && !e.detail.isError) {
    $('#webhook_table_body').addClass('hidden');
    $('#webhook_list_loader').removeClass('hidden');
  }

  /*
  Show error if the response does not have a 20x status code
  */
  if (e.detail.isError) {
    alert('We ran into an error processing your request and will be looking into it. Please try again later.');
  }
});
