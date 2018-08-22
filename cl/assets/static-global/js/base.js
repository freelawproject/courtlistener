/*eslint-env browser */
/*global $, hopscotch */

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
  $('#show-all-statuses').click(function (event) {
    event.preventDefault();
    $('.status-item').removeClass('hidden');
    $('#show-all-statuses').addClass('hidden');
  });

  ///////////////////////
  // Search submission //
  ///////////////////////
  $('#search-form, ' +
    '#sidebar-search-form, ' +
    '.search-page #court-picker-search-form').submit(function (e) {
    e.preventDefault();
    submitSearchForm();
  });

  $('.search-page #id_order_by').change(function () {
    submitSearchForm();
  });

  // Make the enter key work in the search form
  $('.external-input').bind('keypress', function (e) {
    if (e.keyCode == 13) {
      $('#search-form').submit();
    }
  });
  $('#search-button-secondary').click(function (e) {
    $('#search-form').submit();
  });

  $('#advanced-page #court-picker-search-form').submit(function (e) {
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

  $('#court-filter').keyup(courtFilter).change(courtFilter);

  // Check/clear the tab/everything
  $('#check-all').click(function () {
    $('#modal-court-picker .tab-pane input').prop('checked', true);
  });
  $('#clear-all').click(function () {
    $('#modal-court-picker .tab-pane input').prop('checked', false);
  });
  $('#check-current').click(function () {
    $('#modal-court-picker .tab-pane.active input').prop('checked', true);
  });
  $('#clear-current').click(function () {
    $('#modal-court-picker .tab-pane.active input').prop('checked', false);
  });


  ////////////
  // Alerts //
  ////////////
  $('#save-alert-button').click(function (e) {
    e.preventDefault();
    $('#alert-sidebar form').submit();
  });

  $('#id_rate').change(function () {
    if ($(this).val() === 'rt' && totalDonatedLastYear < priceRtAlerts) {
      $('#donate-for-rt').removeClass('hidden');
      $('#alertSave').prop("disabled", true);
    } else {
      // Reset the button, if needed.
      $('#donate-for-rt').addClass('hidden');
      $('#alertSave').prop("disabled", false);
    }
  });

  ///////////////
  // Show More //
  ///////////////
  $(".read-more").click(function (e) {
    e.preventDefault();
    var t = $(this);
    t.parent().find('.more').removeClass('hidden');
    t.addClass('hidden');
  });

  ///////////////////
  // Docket page: Change sort order when the asc/desc buttons are clicked.
  ///////////////////
  $("#sort-buttons :input").change(function () {
    this.closest("form").submit();
  });

  //////////////////////////
  // Popup Cookie Handling//
  //////////////////////////
  $('.alert-dismissible button').click(function () {
    let that = $(this);
    let duration = parseInt(that.data('duration'), 10);
    let cookie_name = that.data('cookie-name');
    let date = new Date();
    date.setTime(date.getTime() + (duration * 24 * 60 * 60 * 1000));
    let expires = "; expires=" + date.toGMTString();
    document.cookie = cookie_name + "=" + 'true' + expires + "; path=/";
    that.closest('.alert-dismissible').addClass('hidden');
  });

  //////////
  // Tour //
  //////////
  var tour = {
    id: 'feature-tour',
    showPrevButton: true,
    steps: [
      {//0
        target: '#search-container',
        placement: 'bottom',
        xOffset: 'center',
        arrowOffset: 'center',
        title: 'Welcome to the Tour!',
        content: 'Broad queries can be a great way to start a ' +
        'research task. Our search box can understand ' +
        'everything you might expect&hellip; terms, concepts, ' +
        'citations, you name it.'
      },
      {//1
        target: '#navbar-o',
        placement: 'bottom',
        arrowOffset: 'left',
        multipage: true,
        nextOnTargetClick: true,
        title: 'More Power Please!',
        content: 'If you are the kind of person that wants more ' +
        'power, you can do advanced searches of opinions, oral ' +
        'arguments or judges by clicking these buttons.' +
        'Click on \"Opinions\" to see the advanced search page.',
        onNext: function () {
          window.location = '/opinion/'
        }
      },
      {//2
        target: '#id_order_by',
        placement: 'top',
        zindex: 10,
        arrowOffset: 'center',
        multipage: true,
        title: 'Sophisticated Search',
        content: 'On the Advanced Search page, you can make ' +
        'sophisticated searches against a variety of fields. ' +
        'Press \"Next\" and we\'ll make a query for you.',

        showPrevButton: false,
        onNext: function () {
          window.location = '/?q=roe+v.+wade&order_by=score+desc&stat_Precedential=on&court=scotus';
        }
      },
      {//3
        // This step will be skipped if on a dev machine with no
        // results. Be not alarmed!
        target: document.querySelector('.search-page article'),
        placement: 'top',
        arrowOffset: 'center',
        zindex: 10,
        title: 'Detailed Results',
        content: 'Here you can see the results for the query "Roe ' +
        'v. Wade" sorted by relevance and filtered to only one ' +
        'jurisdiction, the Supreme Court.',
        showPrevButton: false
      },
      {//4
        target: '#create-alert-header',
        placement: 'top',
        arrowOffset: 'center',
        title: 'Make Alerts',
        content: '<p>Once you have placed a query, you can create ' +
        'an alert. If there are ever any new results for your ' +
        'query, CourtListener will send you an email to keep ' +
        'you up to date.</p> <p>Hit next to check out <em>Roe ' +
        'v. Wade</em>.</p>',
        multipage: true,
        onNext: function () {
          window.location = '/opinion/108713/roe-v-wade/';
        }
      },
      {//5
        target: '#cited-by',
        placement: 'bottom',
        arrowOffset: 'center',
        showPrevButton: false,
        title: 'The Power of Citation',
        content: 'Roe v. Wade has been cited hundreds of times since ' +
        'it was issued in 1973. Looking at these citations can ' +
        'be a good way to see related cases.'
      },
      {//6
        target: '#authorities',
        placement: 'top',
        arrowOffset: 'center',
        title: 'Authorities',
        content: 'The Authorities section lists all of the ' +
        'opinions that Roe v. Wade references. These can be ' +
        'thought of as the principles upon which it rests.',
        multipage: true,
        onNext: function () {
          window.location = '/visualizations/scotus-mapper/'
        }
      },
      {//7
        target: '#new-button a',
        zindex: 2,
        placement: 'bottom',
        arrowOffset: 'center',
        xOffset: 'center',
        showPrevButton: false,
        title: 'Supreme Court Network Visualizations',
        content: '<p>Networks like these show how a line of precedent ' +
        'evolves. You can make your own network to study an area that ' +
        'interests you or look at ones other people have shared.</p>' +
        '<p>For now let\'s skip creating our own and check out what ' +
        'the final product looks like.</p>',
        multipage: true,
        onNext: function () {
          window.location = '/visualizations/scotus-mapper/232/roberts-to-crawford/'
        }
      },
      {//8
        target: "#chart",
        placement: "top",
        arrowOffset: 'center',
        showPrevButton: false,
        xOffset: 'center',
        yOffset: 150,
        title: 'Network Visualizations',
        content: 'Network visualizations have a lot of information. ' +
        'To understand them, consider that the most recent case is on ' +
        'the right and all previous cases are to the left. The ' +
        'further to the left you go, the more heavily cited the cases ' +
        'become.'
      },
      {//9
        target: "form",
        placement: "top",
        arrowOffset: "center",
        xOffset: 'center',
        title: "Different Views",
        content: '<p>Networks can be adjusted to show several ' +
        'different perspectives or Degrees of Separation (DoS). Read ' +
        'the tips in the question marks for more details. There is ' +
        'also more information in the tabs below or you can create ' +
        'your own network to share with others via the button on ' +
        'the right.</p>' +
        '<p>That\'s everything for now. Let us know if ' +
        'you have any questions!</p>',
        onNext: function () {
          hopscotch.endTour();
        }
      }
    ]
  };

  $('.tour-link').click(function (event) {
    event.preventDefault();
    var loc = location.pathname + location.search;
    if (loc !== '/') {
      sessionStorage.setItem('hopscotch.tour.state', 'feature-tour:0');
      window.location = '/';
    } else {
      hopscotch.startTour(tour, 0);
    }
  });
  // Start it automatically for certain steps, if they were directed from
  // another page.
  var autoStartIDs = ['feature-tour:0', 'feature-tour:2', 'feature-tour:3',
    'feature-tour:5', 'feature-tour:7', 'feature-tour:8'];
  if ($.inArray(hopscotch.getState(), autoStartIDs) !== -1) {
    hopscotch.startTour(tour);
  }

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
