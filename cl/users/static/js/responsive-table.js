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

// https://adrianroselli.com/2018/02/tables-css-display-properties-and-aria.html
// https://adrianroselli.com/2018/05/functions-to-add-aria-to-tables-and-lists.html
function AddTableARIA() {
  try {
    var allTables = document.querySelectorAll('table');
    for (var i = 0; i < allTables.length; i++) {
      allTables[i].setAttribute('role', 'table');
    }
    var allRowGroups = document.querySelectorAll('thead, tbody, tfoot');
    for (var i = 0; i < allRowGroups.length; i++) {
      allRowGroups[i].setAttribute('role', 'rowgroup');
    }
    var allRows = document.querySelectorAll('tr');
    for (var i = 0; i < allRows.length; i++) {
      allRows[i].setAttribute('role', 'row');
    }
    var allCells = document.querySelectorAll('td');
    for (var i = 0; i < allCells.length; i++) {
      allCells[i].setAttribute('role', 'cell');
    }
    var allHeaders = document.querySelectorAll('th');
    for (var i = 0; i < allHeaders.length; i++) {
      allHeaders[i].setAttribute('role', 'columnheader');
    }
    // this accounts for scoped row headers
    var allRowHeaders = document.querySelectorAll('th[scope=row]');
    for (var i = 0; i < allRowHeaders.length; i++) {
      allRowHeaders[i].setAttribute('role', 'rowheader');
    }
    // caption role not needed as it is not a real role and
    // browsers do not dump their own role with display block
  } catch (e) {
    console.log('AddTableARIA(): ' + e);
  }
}
document.addEventListener('DOMContentLoaded', function () {
  ResponsiveCellHeaders();
  AddTableARIA();
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
