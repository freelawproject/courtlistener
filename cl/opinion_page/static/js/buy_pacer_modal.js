$(document).ready(function () {
  $('.open_buy_pacer_modal').on('click', function (e) {
    //Modal clicked
    //check if ctrl or shift key pressed
    if (e.metaKey || e.shiftKey) {
      //prevent modal from opening, go directly to href link
      e.stopPropagation();
    } else {
      //otherwise open modal and concatenate pacer URL to button
      let pacer_url = $(this).attr('href');
      $('#modal-buy-pacer #pacer_url').attr('href', pacer_url);
    }
  });


  $('.open_buy_acms_modal').on('click', function (e) {
    //Modal clicked
    //check if ctrl or shift key pressed
    if (e.metaKey || e.shiftKey) {
      //prevent modal from opening, go directly to href link
      e.stopPropagation();
    }else {
      //otherwise open modal and concatenate pacer URL to button
      let pacer_url = $(this).attr('href');
      $('#acms_url').attr('href', pacer_url);
    }
  });

  //////////////////////////
  //  Modal Cookie Handling//
  //////////////////////////
  $('#pacer_url').on('click', function () {
    //on open pacer external url, set buy_on_pacer_modal cookie for 30 days
    let date = new Date();
    date.setTime(date.getTime() + 30 * 24 * 60 * 60 * 1000); //30 days
    let expires = '; expires=' + date.toGMTString();
    document.cookie = 'buy_on_pacer_modal=true' + expires + '; samesite=lax; path=/';

    ///Close Modal
    $('#modal-buy-pacer').modal('toggle');
  });

  $('#acms_url').on('click', function (e) {
    ///Close Modal
    $('#modal-buy-acms').modal('toggle');
  });
});
