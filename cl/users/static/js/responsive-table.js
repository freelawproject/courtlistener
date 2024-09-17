/**
 *  To make a table responsive, add the class `responsive-table-wrapper` to the parent of the <table> element.
 *  To add the header labels to the stacked columns, include the attribute `data-label` in the <th> elements (optional)
 *  */

/**
 * Adds header labels as `::before` pseudo-elements to table cells for mobile views.
 */
function ResponsiveCellHeaders() {
  try {
    var styleElm = document.createElement('style'),
      styleSheet;
    document.head.appendChild(styleElm);
    styleSheet = styleElm.sheet;

    // Select all tables within elements that have the class 'table-wrapper'
    var tables = document.querySelectorAll('.responsive-table-wrapper table');

    tables.forEach(function (table, tableIndex) {
      var ths = table.querySelectorAll('th');
      var tableClass = 'responsive-table-' + tableIndex;
      table.classList.add(tableClass);

      ths.forEach(function (th, index) {
        var headingText = th.getAttribute('data-label');

        if (headingText) {
          // Create a CSS rule that adds the header text as a ::before pseudo-element
          var rule =
            '.' + tableClass + ' td:nth-child(' + (index + 1) + ')::before { content: "' + headingText + ': "; }';

          // Insert the CSS rule into the stylesheet
          styleSheet.insertRule(rule, styleSheet.cssRules.length);
        }
      });
    });
  } catch (e) {
    console.log('ResponsiveCellHeaders(): ' + e);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  ResponsiveCellHeaders();
});

function toggle() {
  const row = window.event.target.closest('tr');
  row.classList.toggle('row-active');

  const isActive = row.classList.contains('row-active');

  if (isActive) {
    const activeColumns = row.querySelectorAll('td:not(:first-child)');
    activeColumns.forEach(function (col) {
      col.setAttribute('aria-hidden', 'false');
    });
  } else {
    const activeColumns = row.querySelectorAll('td[aria-hidden="false"]');
    activeColumns.forEach(function (col) {
      col.setAttribute('aria-hidden', 'true');
    });
  }
}

document.querySelectorAll('td').forEach(function (td) {
  td.addEventListener('click', toggle);
});

function handleResize() {
  const isMobileMode = window.matchMedia('screen and (max-width: 767px)');
  const inactiveColumns = document.querySelectorAll('tbody > tr > td:not(:first-child)');

  inactiveColumns.forEach(function (col) {
    col.setAttribute('aria-hidden', isMobileMode.matches.toString());
  });
}

window.addEventListener('resize', handleResize);

handleResize();
