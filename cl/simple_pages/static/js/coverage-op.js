document.body.addEventListener('htmx:afterRequest', function (event) {
  $('#timeline-body').empty();
});

document.body.addEventListener('htmx:configRequest', function (event) {
  var formData = new URLSearchParams(new FormData(event.srcElement));
  var values = Array.from(formData.values());
  event.detail.parameters = {};
  event.detail.parameters['court_ids'] = values.map(encodeURIComponent).join(',');
  if (values.length === 0) {
    event.preventDefault();
  }
});

function calculateWordWidth(word) {
  //calculate the width we need for the right margin here.
  const span = document.createElement('text');
  span.style.fontSize = '12px';
  span.style.fontFamily = '"Helvetica Neue", Helvetica, Arial, sans-serif;';
  span.style.visibility = 'hidden';
  span.style.position = 'absolute';
  span.textContent = word;
  document.body.appendChild(span);
  const width = span.offsetWidth;
  document.body.removeChild(span);
  return width;
}

function make_data_mobile_friendly(data) {
  // Convert data to mobile chart data
  // Change labels to ID or short citations
  if (Array.isArray(data)) {
    data.forEach((item) => {
      make_data_mobile_friendly(item);
    });
  } else if (typeof data === 'object') {
    if (data.hasOwnProperty('label')) {
      data.label = data.id;
      // console.log(data.label)
    }
    for (const key in data) {
      make_data_mobile_friendly(data[key]);
    }
  }
}

function abbreviate_group_names(data) {
  if (Array.isArray(data)) {
    data.forEach((item) => {
      if (item.group) {
        item.group = item.group
          .replace('Federal', 'Fed.')
          .replace('Appellate', 'App.')
          .replace('Trial', 'Tr.')
          .replace('Special', 'Spec.')
          .replace('Bankruptcy', 'Bank.')
          .replace('Panel', 'Pnl')
          .replace('District', 'Dist.')
          .replace('Supreme', 'Sup.');
      }
    });
  }
}

document.body.addEventListener('htmx:afterSettle', function (event) {
  var results = JSON.parse(event.detail.xhr.response);
  $('#json-data').data('json', JSON.stringify(results));
  $('#fullScreenModal').modal('show');
});

$('#fullScreenModal').on('shown.bs.modal', function () {
  updateChartOnResize();
});

$(document).ready(function () {
  $('.btn-default').on('click', function () {
    var circuitName = $(this).text();
    $('#modalLabel').text(circuitName);
  });
});

$(document).ready(function () {
  // Check if the screen size is xs and automatically toggle the collapse accordingly
  if ($(window).width() < 767) {
    $('#federal_courts').collapse('hide');
    $('#state_courts').collapse('hide');
  }
});

function get_right_margins(results) {
  let right_margin = 0;
  var longest_label;
  results.forEach((group) => {
    group.data.forEach((item) => {
      const labelLength = item.label.length;
      if (labelLength > right_margin) {
        right_margin = labelLength;
        longest_label = item.label;
      }
    });
  });
  return calculateWordWidth(longest_label) + 150;
}

function initializeTimelinesChart() {
  // Try to fit the chart to the size of the users screen
  const container = document.getElementById('timeline-body');
  const containerWidth = container.clientWidth;
  var right_margin;
  var left_margin;
  var jsonData;
  jsonData = $('#json-data').data('json');
  results = JSON.parse(jsonData);
  abbreviate_group_names(results);

  if (containerWidth > 750) {
    right_margin = get_right_margins(results);
    left_margin = 150;
  } else {
    make_data_mobile_friendly(results);
    right_margin = 150;
    left_margin = 0; // drop the margin all together
  }
  this.chart = new TimelinesChart()(`#timeline-body`)
    .zQualitative(false)
    .enableOverview(true)
    .leftMargin(left_margin)
    .rightMargin(right_margin)
    .maxHeight(function (d) {
      return 8000;
    })
    .maxLineHeight(25)
    .data([results[0]])
    .enableAnimations(false)
    .timeFormat('%Y-%m-%d')
    .sortChrono(false)
    .segmentTooltipContent(function (d) {
      const inputDate = new Date(d.timeRange[0]);
      const year = inputDate.getFullYear();
      const inputDate2 = new Date(d.timeRange[1]);
      const year2 = inputDate2.getFullYear();
      if (d.val) {
        return `${year} - ${year2} <br>${d.val} opinions`;
      } else {
        return `${year} - ${year2}`;
      }
    })
    .onSegmentClick(function (d) {
      window.open(`/?court=${d.data.id}`);
    })
    .width(containerWidth)
    .data(results)
    .refresh();
}

function updateChartOnResize() {
  $('#timeline-body').empty();
  initializeTimelinesChart();
}

let resizeTimeout;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    updateChartOnResize();
  }, 100);
});
