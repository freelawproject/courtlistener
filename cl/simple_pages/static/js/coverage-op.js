document.body.addEventListener('htmx:afterRequest', function (event) {
  $('#timeline-body').empty();
});

document.body.addEventListener('htmx:afterSettle', function (event) {
  var results = JSON.parse(event.detail.xhr.response);
  console.log(results);
  TimelinesChart()(`#timeline-body`)
    .zQualitative(false)
    .enableOverview(true)
    .leftMargin(150)
    .rightMargin(400)
    .maxHeight(function (d) {
      return 8000;
    })
    .data(results['r'])
    .enableAnimations(false)
    .timeFormat('%Y-%m-%d')
    .sortChrono(false)
    .segmentTooltipContent(function (d) {
      const inputDate = new Date(d.timeRange[0]);
      const year = inputDate.getFullYear();
      const inputDate2 = new Date(d.timeRange[1]);
      const year2 = inputDate2.getFullYear();
      // ${d.val} Opinion(s)
      return `${year} - ${year2}`;
    })
    .onSegmentClick(function (d) {
      window.open(`https://www.courtlistener.com/?court=${d.val}`);
    })
    .refresh();

  $('#fullScreenModal').modal('show');
});

$(document).ready(function () {
  $('.btn-default').on('click', function () {
    var circuitName = $(this).text();
    $('#modalLabel').text(circuitName);
  });
});
