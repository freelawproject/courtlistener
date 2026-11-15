function showGrowl(message, type) {
  $.bootstrapGrowl(message, {
    type: type,
    align: 'center',
    width: 'auto',
    delay: 2000,
    allow_dismiss: false,
    offset: { from: 'top', amount: 80 },
  });
}

function toggleDocketAlert(e) {
  e.preventDefault();
  let button = $(this),
    icon = button.find('i'),
    // The docket page puts a caret dropdown next to the button that has to
    // change color with it.
    dropdownToggle = button.next('.dropdown-toggle');

  icon.removeClass().addClass('fa fa-spinner fa-pulse');
  $.ajax({
    method: 'POST',
    url: button.attr('href'),
    data: { id: button.data('id') },
    success: function (data) {
      $('.bootstrap-growl').alert('close');
      showGrowl(data, 'success');

      let disabled = /disabled/.test(data);
      icon
        .removeClass()
        .addClass('fa ' + icon.data(disabled ? 'enableIconClass' : 'disableIconClass'));
      button
        .add(dropdownToggle)
        .toggleClass('btn-success', disabled)
        .toggleClass('btn-danger', !disabled);
      button
        .find('.alert_btn_txt')
        .text(button.data(disabled ? 'enableMessage' : 'disableMessage'));
    },
    error: function () {
      showGrowl('An error occurred. Please try again.', 'danger');
    },
  });
}

$(document).ready(function () {
  $('.toggle-docket-alert').on('click', toggleDocketAlert);
});
