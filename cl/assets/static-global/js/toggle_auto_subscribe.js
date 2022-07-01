function toggleSwitchButton(value){
  value.classList.toggle('btn-primary');
  value.classList.toggle('btn-light');
  value.classList.toggle('off');
}

document.body.addEventListener('htmx:afterRequest', function (event) {
  $('.bootstrap-growl').alert("close");
  if (event.detail.failed == false) {
    let switchButton = document.getElementById("switch-button");
    toggleSwitchButton(switchButton);
     $.bootstrapGrowl(
      event.detail.xhr.responseText,
      {
        type: "success",
        align: "center",
        width: "auto",
        delay: 2000,
        allow_dismiss: false,
        offset: {from: 'top', amount: 80}
      }
    );
  } else {
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
