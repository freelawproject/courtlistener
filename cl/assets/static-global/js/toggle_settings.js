$(document).ready(function () {
  $('.toggle-docket-alert, .toggle-monthly-donation').click(function(e){
    e.preventDefault();
    let button = $(this),
        id = button.data('id'),
        enable_message = button.data('enableMessage'),
        disable_message = button.data('disableMessage'),
        button_icon = button.find('i'),
        button_enable_class = button_icon.data('enableIconClass'),
        button_disable_class = button_icon.data('disableIconClass'),
        alert_text = button.find('.alert_btn_txt'),
        url = button.attr('href');

    button_icon
      .removeClass()
      .addClass('fa fa-spinner fa-pulse');
    $.ajax({
      method: 'POST',
      url: url,
      data: {'id': id},
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
            .removeClass()
            .addClass("fa " + button_enable_class);
          button
            .removeClass("btn-danger")
            .addClass("btn-success");
          alert_text.text(enable_message);
        } else {
          button_icon
            .removeClass()
            .addClass("fa " + button_disable_class);
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
