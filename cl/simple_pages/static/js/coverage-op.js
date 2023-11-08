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

function update_labels(data, is_scraper = false) {
  data.forEach((item) => {
    Object.keys(item).forEach((key) => {
      if (key === 'data') {
        update_labels(item[key], item.group == "Scrapers");
      }
      if (key === 'label') {
        if (is_scraper) {
          item['label'] = item['id'] + " (scraper)";
        }else {
          item['label'] = item['id'];
        }
      }
    });
  });
}

const ALL_GROUP_TO_ABBREVIATIONS = {
  'Federal Appellate': 'Fed. App.',
  'Federal District': 'Fed. Dist.',
  'Federal Bankruptcy': 'Fed. Bankr.',
  'Federal Bankruptcy Panel': 'Fed. Bankr. Pan.',
  'Federal Special': 'Fed. Spec.',
  'State Supreme': 'State Sup.',
  'State Appellate': 'State App.',
  'State Trial': 'State Tri.',
  'State Special': 'State Spec.',
  'Tribal Supreme': 'Trib. Sup.',
  'Tribal Appellate': 'Trib. App.',
  'Tribal Trial': 'Trib. Trial',
  'Tribal Special': 'Trib. Spec.',
  'Territory Supreme': 'Terr. Sup.',
  'Territory Appellate': 'Terr. App.',
  'Territory Trial': 'Terr. Trial',
  'Territory Special': 'Terr. Spec.',
  'State Attorney General': 'St. Att. Gen.',
  'Military Appellate': 'Mil. App.',
  'Military Trial': 'Mil. Trial',
  'Committee': 'Comm.',
  'International': 'Int.',
  'Scrapers': 'Scrapers'
};

function abbreviate_group_names(data) {
  if (Array.isArray(data)) {
    data.forEach((item) => {
      if (item.group) {
        item.group = ALL_GROUP_TO_ABBREVIATIONS[item.group];
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

function getTextWidth(text) {
  // re-use canvas object for better performance
  const canvas = getTextWidth.canvas || (getTextWidth.canvas = document.createElement('canvas'));
  const context = canvas.getContext('2d');
  // use the style of the tooltips to avoid overflow
  context.font = 'bold 13px sans-serif';
  const metrics = context.measureText(text);
  return Math.ceil(metrics.width);
}

function get_right_margins(results, smallScreen = false) {
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
  let width = getTextWidth(longest_label)
  let padding = smallScreen ? 0 : 20;
  return width + padding;
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
    right_margin = get_right_margins(results, false);
    left_margin = 150;
  } else {
    update_labels(results);
    right_margin = get_right_margins(results, true);
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
    .disableReduceLabels(true)
    .enableAnimations(false)
    .timeFormat('%Y-%m-%d')
    .sortChrono(false)
    .segmentTooltipContent(function (d) {
      const inputDate = new Date(d.timeRange[0]);
      const year = inputDate.getFullYear();
      const inputDate2 = new Date(d.timeRange[1]);
      const year2 = inputDate2.getFullYear();
      return `${year} - ${year2}`;
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
