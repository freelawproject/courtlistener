$(document).ready(function () {
    $(".open_buy_pacer_modal").on("click", function (e) {
        //Modal clicked
        //check if ctrl or shift key pressed
        if (e.metaKey || e.shiftKey){
            //prevent modal from opening, go directly to href link
            e.stopPropagation();
        }
        else{
            //otherwise open modal and concatenate pacer URL to button
            var pacer_url = $(this).attr('href');
            $("#modal-buy-pacer #pacer_url").attr("href", pacer_url);
        }
    });

  //////////////////////////
  //  Modal Cookie Handling//
  //////////////////////////
  $('#pacer_url').on("click", function () {
    //on open parcer external url, set buy_on_pacer_modal cookie for 30 days
    let that = $(this);
    let duration = parseInt(that.data('duration'), 10);
    let cookie_name = that.data('cookie-name');
    let date = new Date();
    date.setTime(date.getTime() + (duration * 24 * 60 * 60 * 1000)); //30 days
    let expires = "; expires=" + date.toGMTString();
    document.cookie = cookie_name + "=" + 'true' + expires + "; path=/";

    ///Close Modal
    $("#modal-buy-pacer ").modal('toggle');
  });
});