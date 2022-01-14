$(document).ready(function () {


    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
          var cookies = document.cookie.split(';');
          for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) == (name + '=')) {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
            }
          }
        }
        return cookieValue;
      }

    
    $("#open_buy_pacer_modal").on("click", function (e) {

        //Modal clicked


        var recap_installed = getCookie('recap_install_plea');
        //check if recap is installed or ctrl or shift key pressed
        if (recap_installed || e.metaKey || e.shiftKey){
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

    let that = $(this);
    let duration = parseInt(that.data('duration'), 10);
    let cookie_name = that.data('cookie-name');
    let date = new Date();
    date.setTime(date.getTime() + (duration * 24 * 60 * 60 * 1000));
    let expires = "; expires=" + date.toGMTString();
    document.cookie = cookie_name + "=" + 'true' + expires + "; path=/";

    ///Close Modal
    $("#modal-buy-pacer ").modal('toggle');
    
  });


});