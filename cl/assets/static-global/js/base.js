/*eslint-env browser */
/*global $ */

function recapIsInstalled(event) {
  // Check the event that's returned by the extension and return whether it
  // indicates that RECAP is installed.
  return !!(
    event.source === window &&
    event.data.sender &&
    event.data.sender === "recap-extension" &&
    event.data.message_name &&
    event.data.message_name === "version"
  );
}

$(document).ready(function () {
  // 'use strict'; // uncomment later on after full cleanup
  var citedGreaterThan = $('#id_cited_gt');
  var citedLessThan = $('#id_cited_lt');

  function submitSearchForm() {
    // Ensure that the correct value is set in the radio button (correct
    // is defined by the label that is .selected). This is needed because
    // the "wrong" value will be selected after a user presses the back
    // button in their browser.
    $('#type-switcher .selected input').prop('checked', true);

    // Empty the sliders if they are both at their max
    if (citedGreaterThan.val() === 0 && citedLessThan.val() === 20000) {
      // see https://github.com/freelawproject/courtlistener/issues/303
      citedGreaterThan.val('');
      citedLessThan.val('');
    }

    // Gather all form fields that are necessary
    var gathered = $();

    // Add the input boxes that aren't empty
    var selector = '.external-input[type=text]';
    gathered = gathered.add($(selector).filter(function () {
      return this.value !== '';
    }));

    selector = 'select.external-input';
    gathered = gathered.add($(selector).filter(function () {
      return this.value !== '';
    }));

    // Add selected radio buttons
    gathered = gathered.add($('.external-input[type=radio]:checked'));

    // Add the court checkboxes that are selected as a single input element
    var checkedCourts = $('.court-checkbox:checked');
    if (checkedCourts.length !== $('.court-checkbox').length) {
      // Only do this if all courts aren't checked to keep URLs short.
      var values = [];
      for (var i = 0; i < checkedCourts.length; i++) {
        values.push(checkedCourts[i].id.split('_')[1]);
      }
      var courtString = values.join(' ');
      var el = jQuery('<input/>', {
        value: courtString,
        name: 'court'
      });
    }
    gathered = gathered.add(el);

    if ($('.status-checkbox:checked').length <= $('.status-checkbox').length) {
      // Add the status checkboxes that are selected
      gathered = gathered.add($('.status-checkbox:checked'));
    }

    gathered = gathered.add($('#id_available_only:checked'));

    // Add the hidden input used to indicate that we're editing an existing
    // alert
    gathered = gathered.add($('input[name=edit_alert]'));

    // Remove any inputs that are direct children of the form. These are
    // pernicious leftovers caused by the evils of the back button.
    $('#search-form > input').remove();

    gathered.each(function () {
      // Make and submit a hidden input element for all gathered fields
      var el = $(this);
      $('<input type="hidden" name="' + el.attr('name') + '" />')
        .val(el.val())
        .appendTo('#search-form');
    });
    document.location = '/?' + $('#search-form').serialize();
  }

  // Statuses
  $('#show-all-statuses').on("click", function (event) {
    event.preventDefault();
    $('.status-item').removeClass('hidden');
    $('#show-all-statuses').addClass('hidden');
  });

  ///////////////////////
  // Search submission //
  ///////////////////////
  $('#search-form, ' +
    '#sidebar-search-form, ' +
    '.search-page #court-picker-search-form').on("submit", function (e) {
    e.preventDefault();
    submitSearchForm();
  });

  $('.search-page #id_order_by').on("change", function () {
    submitSearchForm();
  });

  // Make the enter key work in the search form
  $('.external-input').on('keypress', function (e) {
    if (e.keyCode == 13) {
      $('#search-form').submit();
    }
  });
  $('#search-button-secondary').on("click", function (e) {
    $('#search-form').submit();
  });

  $('#advanced-page #court-picker-search-form').on("submit", function (e) {
    e.preventDefault();

    // Indicate the count of selected jurisdictions when switching to
    // advanced search page.
    $('#jurisdiction-count').text($(this).find('input:checked').length);
    $('#court-picker').modal('hide');
  });


  //////////////////
  // Court Picker //
  //////////////////
  function courtFilter() {
    var tabs = $('.tab-content'),
      checkboxes = tabs.find('.checkbox'),
      regex = new RegExp('\\b' + this.value, 'i'),
      matches = checkboxes.filter(function () {
        return regex.test($(this).find('label').text());
      });
    checkboxes.not(matches).find('input').prop('checked', false);
    matches.find('input').prop('checked', true);
  }

  $('#court-filter').on("keyup", courtFilter).on("change", courtFilter);

  // Check/clear the tab/everything
  $('#check-all').on("click", function () {
    $('#modal-court-picker .tab-pane input').prop('checked', true);
  });
  $('#clear-all').on("click", function () {
    $('#modal-court-picker .tab-pane input').prop('checked', false);
  });
  $('#check-current').on("click", function () {
    $('#modal-court-picker .tab-pane.active input').prop('checked', true);
  });
  $('#clear-current').on("click", function () {
    $('#modal-court-picker .tab-pane.active input').prop('checked', false);
  });


  ////////////
  // Alerts //
  ////////////
  $('#id_rate').on("change", function () {
    if ($(this).val() === 'rt' && totalDonatedLastYear < priceRtAlerts) {
      $('#donate-for-rt').removeClass('hidden');
      $('#alertSave').prop("disabled", true);
    } else {
      // Reset the button, if needed.
      $('#donate-for-rt').addClass('hidden');
      $('#alertSave').prop("disabled", false);
    }
  });

  ///////////////////////////
  // TOC Collapse Controls //
  ///////////////////////////

  // when element moves from hidden to shown
  $('.collapse').on('shown.bs.collapse', function () {
    // the element's id is the parent element's href target
    $targetId = $(this).attr('id')

    // "collapse in" check ensures only direct parent affected
    // the directly related parent element is edited
    if($(this).attr("class") === "collapse in") {
      $(`[href="#${$targetId}"]`).html("[–]")
    }
  })

  // when element moves from shown to hidden
  $('.collapse').on('hidden.bs.collapse', function () {
    // the element's id is the parent element's href target
    $targetId = $(this).attr('id')

    // "collapse" check ensures only direct parent affected
    if($(this).attr("class") === "collapse") {
      $(`[href="#${$targetId}"]`).html("[+]")
    }
  })

  ///////////////
  // Show More //
  ///////////////
  $(".read-more").on("click", function (e) {
    e.preventDefault();
    var t = $(this);
    t.parent().find('.more').removeClass('hidden');
    t.addClass('hidden');
  });

  ///////////////////
  // Docket page: Change sort order when the asc/desc buttons are clicked.
  ///////////////////
  $("#sort-buttons :input").on("change", function () {
    this.closest("form").submit();
  });

  //////////////////////////
  // Popup Cookie Handling//
  //////////////////////////
  $('.alert-dismissible button').on("click", function () {
    let that = $(this);
    let duration = parseInt(that.data('duration'), 10);
    let cookie_name = that.data('cookie-name');
    let date = new Date();
    date.setTime(date.getTime() + (duration * 24 * 60 * 60 * 1000));
    let expires = "; expires=" + date.toGMTString();
    document.cookie = cookie_name + "=" + 'true' + expires + "; path=/";
    that.closest('.alert-dismissible').addClass('hidden');
  });

  ///////////////////////
  // Utility Functions //
  ///////////////////////
  // Make sure that a CSRF Header is sent with every ajax request.
  // https://docs.djangoproject.com/en/dev/ref/csrf/#ajax
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
  var csrfToken = getCookie('csrftoken');

  function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
  }

  $.ajaxSetup({
    beforeSend: function (xhr, settings) {
      if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
        xhr.setRequestHeader("X-CSRFToken", csrfToken);
      }
    }
  });

  $('[data-toggle="tooltip"]').tooltip();

  // Hide RECAP install pleas for people that already have it, and set a cookie
  // so they won't see the page flash each time.
  window.addEventListener("message", function (event) {
    if (recapIsInstalled(event)){
      $(".recap_install_plea").addClass('hidden');
      let date = new Date();
      date.setTime(date.getTime() + (7 * 24 * 60 * 60 * 1000)); // 7 days
      let expires = "; expires=" + date.toGMTString();
      document.cookie = "recap_install_plea" + "=" + 'true' + expires + "; path=/";
    }
  });

  // Append the base docket query to the user input and submit the search.
  function submit_search_query(selector_id) {
    window.location = $(selector_id).attr('href') + ' ' + $('#de-filter-search').val();
    return false;
  }
  // Make the docket entries search box work on click.
  $('#search-button-de-filter').on('click', function (e) {
    e.preventDefault();
    submit_search_query('#search-button-de-filter');
  });
  // Make the docket entries search box work on "Enter".
  $('#de-filter-search').on('keypress', function (e) {
    if (e.keyCode == 13) {
      submit_search_query('#search-button-de-filter');
    }
  });

});



// Debounce - rate limit a function
// https://davidwalsh.name/javascript-debounce-function
function debounce(func, wait, immediate) {
  // Returns a function, that, as long as it continues to be invoked, will not
  // be triggered. The function will be called after it stops being called for
  // N milliseconds. If `immediate` is passed, trigger the function on the
  // leading edge, instead of the trailing.
  var timeout;
  return function () {
    var context = this, args = arguments;
    var later = function () {
      timeout = null;
      if (!immediate) func.apply(context, args);
    };
    var callNow = immediate && !timeout;
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
    if (callNow) func.apply(context, args);
  };
};

/*
  Method to copy the content from a textarea to the clipboard.
*/
function copy_text(selector_id) {
  let text_area = document.getElementById(selector_id).closest('textarea');
  text_area.select();
  navigator.clipboard.writeText(text_area.value);
}
