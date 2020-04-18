$(document).ready(function () {
  window.addEventListener("message", function (event){
    // If RECAP is installed, check whether we should allow this person to
    // make more alerts. If so, tweak the events on the button to create
    // the alert, not to show the "too many alerts" modal. Note that this
    // is pretty nasty because we're introducing Django variables into our
    // JavaScript code.
    bad_class = 'no-more-alerts-modal-trigger';
    if (recapIsInstalled(event)){
      console.log("You have RECAP installed. Applying docket alert bonus.");
      let total_allowed_alerts = maxFreeDocketAlerts + recapBonusAlerts;
      if (userAlertCount < total_allowed_alerts){
        // Disable the "Too many alerts" popup, and enable the function to
        // toggle settings.
        anchors = $('.' + bad_class);
        anchors.off();
        anchors.on("click", toggleSettings);
      }
    }
  });

  // If we have classes indicating too many alerts or logged out users,
  // activate their modals.
  $(".no-more-alerts-modal-trigger").on("click", function(e){
    e.preventDefault();
    $("#modal-no-more-alerts").modal('toggle');
  });
  $(".logged-out-modal-trigger").on("click", function(e) {
    e.preventDefault();
    $("#modal-logged-out").modal('toggle');
  });

});

