
////////////////
// Pagination //
////////////////

// Star pagination weirdness for ANON 2020 dataset -

$('.star-pagination').each(function (index, element) {
  if ($(this).attr('pagescheme')) {
    // For ANON 2020 this has two sets of numbers but only one can be
    // verified with other databses so only showing one
    var number = $(this).attr('number');
    if (number.indexOf('P') > -1) {
      $(this).attr('label', '');
    } else {
      $(this).attr('label', number);
    }
  } else {
    $(this).attr('label', this.textContent.trim().replace('*Page ', ''));
  }
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

  // This is needed for variations in resource.org footnotes
// This is needed for variations in resource.org footnotes
$('.footnotes > .footnote').each(function () {
  var $this = $(this);
  var newElement = $('<footnote />'); // Create a new <footnote> element

  // Copy attributes and content from the original element
  $.each(this.attributes, function (_, attr) {
    newElement.attr(attr.name, attr.value);
  });
  newElement.html($this.html()); // Copy the inner content
  $this.replaceWith(newElement); // Replace the original <div> with <footnote>
});


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
    const $newElement = $('<a></a>');
    // Copy attributes from the old element
    $.each(footnoteMark.attributes, function () {
      if (footnoteMark.specified) {
        $newElement.attr(footnoteMark.name, footnoteMark.value);
      }
    });
    $newElement.html(footnoteMark.html());
    const $supElement = $('<sup></sup>').append($newElement);
    footnoteMark.replaceWith($supElement);
    const footnote = footnotes.eq(index);
    $newElement.attr('href', `#fn${index}`);
    $newElement.attr('id', `fnref${index}`);
    footnote.attr('id', `fn${index}`);

    const $jumpback = $('<a class="jumpback">↵</a>');
    $jumpback.attr('href', `#fnref${index}`);

    footnote.append($jumpback);
  });
} else {
  //   If the number of footnotes and footnotemarks are inconsistent use the method to scroll to the nearest one
  //   we dont use this by default because many older opinions will reuse *  ^ and other icons repeatedly on every page
  //   and so label is no usable to identify the correct footnote.

  footnotes.each(function (index) {
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
      // console.warn('No matching footnote found below the current position for:', markText);
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
      // console.warn('No matching footnotemark found above the current position for label:', footnoteLabel);
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
  let currentSection = '';

  // Determine which section is currently in view
  sections.forEach((section) => {
    let sectionTop = section.offsetTop;
    let sectionHeight = section.offsetHeight;
    if (window.scrollY >= sectionTop - sectionHeight / 3) {
      currentSection = section.getAttribute('id');
    }
  });
  if (!currentSection) currentSection = 'top';
  // Remove the active class from links and their parent elements
  let links = document.querySelectorAll('.jump-links > a.active');
  links.forEach((link) => {
    link.classList.remove('active');
    if (link.parentElement) {
      link.parentElement.classList.remove('active');
    }
  });

  // Add the active class to the link and its parent that corresponds to the current section
  let activeLink = document.getElementById(`nav_${currentSection}`);
  if (!activeLink) return;

  activeLink.classList.add('active');
  if (activeLink.parentElement) {
    activeLink.parentElement.classList.add('active');
  }
});

document.querySelectorAll("page-label").forEach(label => {
    label.addEventListener("click", function() {
        const href = this.getAttribute("href");
        if (href) {
            window.location.href = href;
        }
    });
});