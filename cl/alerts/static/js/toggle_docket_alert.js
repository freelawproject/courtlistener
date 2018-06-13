$(document).ready(function () {
  $('.toggle-docket-alert').click(function(e){
    e.preventDefault();
    let button = $(this),
        docket_id = button.data('docketId'),
        enable_message = button.data('enableMessage'),
        disable_message = button.data('disableMessage'),
        button_icon = button.find('i'),
        alert_text = button.find('.alert_btn_txt'),
        url = button.attr('href');

    button_icon
      .removeClass("fa-bell-slash-o")
      .removeClass("fa-bell")
      .addClass('fa-spinner fa-pulse');
    $.ajax({
      method: 'POST',
      url: url,
      data: {'docket_id': docket_id},
      success: function(data){
        $('.bootstrap-growl').alert("close");
        $.bootstrapGrowl(
          data,
          {
            type: "success",
            align: "center",
            width: "auto",
            delay: 2000,
            allow_dismiss: false,
            offset: {from: 'top', amount: 80}
          }
        );
        if (/disabled/g.exec(data)) {
          button_icon
            .removeClass("fa-spinner fa-pulse")
            .addClass("fa-bell");
          button
            .removeClass("btn-danger")
            .addClass("btn-success");
          alert_text.text(enable_message);
        } else {
          button_icon
            .removeClass("fa-spinner fa-pulse")
            .addClass("fa-bell-slash-o");
          button
            .removeClass("btn-success")
            .addClass("btn-danger");
          alert_text.text(disable_message);
        }
      },
      error: function (data) {
        $.bootstrapGrowl(
          "An error occurred. Please try again.",
          {
            type: "danger",
            align: "center",
            width: "auto",
            delay: 2000,
            allow_dismiss: false,
            offset: {from: 'top', amount: 80}
          }
        );
      }
    });
  });
});
