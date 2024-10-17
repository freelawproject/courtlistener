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
    installProgressBar();
    disableAllSubmitButtons();
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
    if ($(this).val() === 'rt' && !isMember) {
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
    document.cookie = cookie_name + "=" + 'true' + expires + "; samesite=lax; path=/";
    that.closest('.alert-dismissible').addClass('hidden');
  });

  ///////////////////////
  // Utility Functions //
  ///////////////////////
  // Make sure that a CSRF Header is sent with every ajax request.
  // https://docs.djangoproject.com/en/dev/ref/csrf/#ajax
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
      document.cookie = "recap_install_plea" + "=" + 'true' + expires + "; samesite=lax; path=/";
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
  // Open the #open-modal-on-load modal on page load if it exists in a page.
  const modal_exist = document.getElementById('open-modal-on-load');
  if (modal_exist) {
    $('#open-modal-on-load').modal();
  }
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
  Register event handler for copy-to-clipboard buttons.
*/
function handleClipboardCopyClick(event) {
  let clipboardCopySource = event.target.closest("[data-clipboard-copy-target]")
  let clipboardCopyTargetId = clipboardCopySource && clipboardCopySource.dataset.clipboardCopyTarget;
  let clipboardCopyTarget = clipboardCopyTargetId && document.getElementById(clipboardCopyTargetId);
  if (clipboardCopyTarget) {
    clipboardCopyTarget.select();
    if (navigator.clipboard) { //
      navigator.clipboard.writeText(clipboardCopyTarget.value);
    }
  }
};
document.addEventListener('click', handleClipboardCopyClick);

/*
  Register event handler for copy-to-clipboard inputs.
*/
function handleClipboardTextClick(event) {
  if (event.target.classList.contains("click-select")) {
    event.target.select();
  }
};
document.addEventListener('click', handleClipboardTextClick);

/*
  Disable the signup form submit button on submit to avoid repeated submissions.
*/
const form = document.getElementById('register-form');
let button = document.getElementById('register-button');
if (form && button) {
  form.addEventListener('submit', function () {
    button.disabled = true;
  });
}

//////////////////
// SCOTUS STYLE //
//////////////////

document.querySelectorAll('p').forEach(function (element) {
  // Bold and Center likely Roman Numerals this improves SCOTUS opinions
  if (element.textContent.trim().length < 5) {
    element.classList.add('center-header');
  }
});


////////////////
// Pagination //
////////////////

$('.star-pagination').each(function (index, element) {
  $(this).attr('label', this.textContent.trim().replace('*Page ', ''));
});

// Systematize page numbers
$('page-number').each(function (index, element) {
  // Get the label and citation index from the current element
  const label = $(this).attr('label');
  const citationIndex = $(this).attr('citation-index');

  // Clean up the label (remove '*') and use it for the new href and id
  const cleanLabel = label.replace('*', '').trim();

  // Create the new <a> element
  const $newAnchor = $('<a></a>')
    .addClass('page-label')
    .attr('data-citation-index', citationIndex)
    .attr('data-label', cleanLabel)
    .attr('href', '#' + cleanLabel)
    .attr('id', cleanLabel)
    .text('*' + cleanLabel);

  // Replace the <page-number> element with the new <a> element
  $(this).replaceWith($newAnchor);
});

// Systematize page numbers
$('span.star-pagination').each(function (index, element) {
  // Get the label and citation index from the current element
  const label = $(this).attr('label');
  const citationIndex = $(this).attr('citation-index');

  // Clean up the label (remove '*') and use it for the new href and id
  const cleanLabel = label.replace('*', '').trim();

  // Create the new <a> element
  const $newAnchor = $('<a></a>')
    .addClass('page-label')
    .attr('data-citation-index', citationIndex)
    .attr('data-label', cleanLabel)
    .attr('href', '#' + cleanLabel)
    .attr('id', cleanLabel)
    .text('*' + cleanLabel);

  // Replace the <span> element with the new <a> element
  $(this).replaceWith($newAnchor);
});
// Fix weird data-ref bug
document.querySelectorAll('strong').forEach((el) => {
  if (/\[\d+\]/.test(el.textContent)) {
    // Check if the text matches the pattern [XXX]
    const match = el.textContent.match(/\[\d+\]/)[0]; // Get the matched pattern
    el.setAttribute('data-ref', match); // Set a data-ref attribute
  }
});

///////////////
// Footnotes //
///////////////

// We formatted the harvard footnotes oddly when they appeared inside the pre-opinion content.
// this removes the excess a tags and allows us to standardize footnotes across our contents
// footnote cleanup in harvard
// Update and modify footnotes to enable linking
$('div.footnote > a').remove();
const headfootnotemarks = $('a.footnote');
const divfootnotes = $('div.footnote');

if (headfootnotemarks.length === divfootnotes.length) {
  headfootnotemarks.each(function (index) {
    const footnoteMark = $(this);
    const footnote = divfootnotes.eq(index);

    const $newElement = $('<footnotemark></footnotemark>');
    $.each(footnoteMark.attributes, function () {
      if (footnoteMark.specified) {
        $newElement.attr(footnoteMark.name, footnoteMark.value);
      }
    });
    $newElement.html(footnoteMark.html());
    footnoteMark.replaceWith($newElement);

    const $newFootnote = $('<footnote></footnote>');
    $.each(footnote.attributes, function () {
      if (footnote.specified) {
        $newFootnote.attr(footnote.name, footnote.value);
      }
    });
    $newFootnote.attr('label', footnote.attr('label'));
    $newFootnote.html(footnote.html());
    footnote.replaceWith($newFootnote);
  });
}

// This fixes many of the harvard footnotes so that they can
// easily link back and forth - we have a second set
// of harvard footnotes inside headnotes that need to be parsed out now
// okay.

const footnoteMarks = $('footnotemark');
const footnotes = $('footnote').not('[orphan="true"]');

if (footnoteMarks.length === footnotes.length) {
  // we can make this work
  footnoteMarks.each(function (index) {
    const footnoteMark = $(this);
    console.log(index, footnoteMark);
    const $newElement = $('<a></a>');
    // Copy attributes from the old element
    $.each(footnoteMark.attributes, function () {
      if (footnoteMark.specified) {
        $newElement.attr(footnoteMark.name, footnoteMark.value);
        console.log(footnoteMark.name, footnoteMark.value);
      }
    });
    $newElement.html(footnoteMark.html());
    const $supElement = $('<sup></sup>').append($newElement);
    footnoteMark.replaceWith($supElement);
    const footnote = footnotes.eq(index);
    $newElement.attr('href', `#fn${index}`);
    $newElement.attr('id', `fnref${index}`);
    footnote.attr('id', `fn${index}`);
    console.log(footnoteMark, footnote);

    const $jumpback = $('<a class="jumpback">↵</a>');
    $jumpback.attr('href', `#fnref${index}`);

    footnote.append($jumpback);
  });
} else {
  //   If the number of footnotes and footnotemarks are inconsistent use the method to scroll to the nearest one
  //   we dont use this by default because many older opinions will reuse *  ^ and other icons repeatedly on every page
  //   and so label is no usable to identify the correct footnote.

  footnotes.each(function (index) {
    console.log($(this));

    const $jumpback = $('<a class="jumpback">↵</a>');
    $jumpback.attr('label', $(this).attr('label'));
    $(this).append($jumpback);
  });

  // There is no silver bullet for footnotes
  $('footnotemark').on('click', function () {
    const markText = $(this).text().trim(); // Get the text of the clicked footnotemark
    const currentScrollPosition = $(window).scrollTop(); // Get the current scroll position

    // Find the first matching footnote below the current scroll position
    const targetFootnote = $('footnote')
      .filter(function () {
        return $(this).attr('label') === markText && $(this).offset().top > currentScrollPosition;
      })
      .first();

    // If a matching footnote is found, scroll to it
    if (targetFootnote.length > 0) {
      $('html, body').animate(
        {
          scrollTop: targetFootnote.offset().top,
        },
        500
      ); // Adjust the animation duration as needed
    } else {
      console.warn('No matching footnote found below the current position for:', markText);
    }
  });


  //////////////
  // Sidebar //
  /////////////

  $('.jumpback').on('click', function () {
    const footnoteLabel = $(this).attr('label').trim(); // Get the label attribute of the clicked footnote
    const currentScrollPosition = $(window).scrollTop(); // Get the current scroll position

    // Find the first matching footnotemark above the current scroll position
    const targetFootnotemark = $('footnotemark')
      .filter(function () {
        return $(this).text().trim() === footnoteLabel && $(this).offset().top < currentScrollPosition;
      })
      .last();

    // If a matching footnotemark is found, scroll to it
    if (targetFootnotemark.length > 0) {
      $('html, body').animate(
        {
          scrollTop: targetFootnotemark.offset().top,
        },
        500
      ); // Adjust the animation duration as needed
    } else {
      console.warn('No matching footnotemark found above the current position for label:', footnoteLabel);
    }
  });
}

$(document).ready(function () {
  function adjustSidebarHeight() {
    if ($(window).width() > 767) {
      // Only apply the height adjustment for screens wider than 767px
      var scrollTop = $(window).scrollTop();
      if (scrollTop <= 175) {
        $('.opinion-sidebar').css('height', 'calc(100vh - ' + (175 - scrollTop) + 'px)');
        // $('.main-document').css('height', 'calc(100vh + ' + (scrollTop) + 'px)');
      } else {
        $('.opinion-sidebar').css('height', '100vh');
      }
    } else {
      $('.opinion-sidebar').css('height', 'auto'); // Reset height for mobile view
    }
  }

  // Adjust height on document ready and when window is scrolled or resized
  adjustSidebarHeight();
  $(window).on('scroll resize', adjustSidebarHeight);
});

// Update sidebar to show where we are on the page
document.addEventListener('scroll', function () {
  let sections = document.querySelectorAll('.jump-link');
  let links = document.querySelectorAll('.jump-links > a');
  let currentSection = '';

  // Determine which section is currently in view
  sections.forEach((section) => {
    let sectionTop = section.offsetTop;
    let sectionHeight = section.offsetHeight;
    if (window.scrollY >= sectionTop - sectionHeight / 3) {
      currentSection = section.getAttribute('id');
    }
  });

  // Remove the active class from all links and their parent elements
  links.forEach((link) => {
    link.classList.remove('active');
    if (link.parentElement) {
      link.parentElement.classList.remove('active');
    }
  });

  // Add the active class to the link and its parent that corresponds to the current section
  links.forEach((link) => {
    if (link.getAttribute('href') === `#${currentSection}`) {
      link.classList.add('active');
      if (link.parentElement) {
        link.parentElement.classList.add('active');
      }
    }
  });
});
