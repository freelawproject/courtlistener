/*eslint-env browser */
/*global $, sorted_courts, precedentTypes */
var hash = window.location.hash.substr(1),
    court_data = {}, // populated by addNavigation
    chartData = [], // extracted from API
    currentData = new Plottable.Dataset([]),
    xLabel = new Plottable.Components.Label(''),
    title = new Plottable.Components.TitleLabel(),
    table = {},
    opinionCount = 0;
function hashCheck() {
    if (hash === '' || !(hash in court_data)) {
        hash = 'all'
    }
}
function updateTitle(){
    title.text(opinionCount.toLocaleString() + ' Opinions');
}

/**
 * draw the graph and add the interactions we want
 */
function drawGraph() {
    var xScale = new Plottable.Scales.Linear(),
        xAxis = new Plottable.Axes.Numeric(xScale, 'bottom')
            .formatter(new Plottable.Formatters.fixed(0)),
        yScale = new Plottable.Scales.Linear(),
        yLabel = new Plottable.Components.Label(),
        yAxis  = new Plottable.Axes.Numeric(yScale, 'left'),
        plot = new Plottable.Plots.Bar(),
        pointer = new Plottable.Interactions.Pointer(),
        click = new Plottable.Interactions.Click();

    d3.select('#chart')
        .append('svg')
        .attr('id', 'coverageChart')
        .attr('height', '400px');
    // Plot Components
    updateTitle();
    yLabel.text('Number of Opinions')
        .angle(-90);
    xLabel.text(court_data[hash].short_name);
    currentData.data(chartData);
    plot.addDataset(currentData)
        .animated(true)
        .x(function(d) { return d.x}, xScale)
        .y(function(d) { return d.y}, yScale)
        .labelsEnabled(true)
        .attr('fill', "#AE0B0B");
    yAxis.formatter(function (d) {
        return d.toLocaleString();
    });

    table = new Plottable.Components.Table([
        [null, null, title],
        [yLabel, yAxis, plot],
        [null, null, xAxis],
        [null, null, xLabel]
    ]);

    pointer.onPointerMove(function(p){
        var entity = plot.entityNearest(p);
        var xString = entity.datum.x;
        var yString = entity.datum.y;
        title.text(yString + " opinions in " + xString);
    });
    pointer.onPointerExit(function(p) {
        title.text(opinionCount.toLocaleString() + ' Opinions');
    });
    pointer.attachTo(plot);

    click.onClick(function(p) {
        var bars = plot.entitiesAt(p),
            year,
            precedentString = '',
            i;
        if (bars.length) {
            year = bars[0].datum.x;
            for (i = 0; i < precedentTypes.length; i++) {
                precedentString += '&' + precedentTypes[i] + '=on';
            }
            window.location.href = '/?filed_after=' + year +
                '&filed_before=' + year +
                precedentString +
                ((hash !== 'all') ? '&court=' + hash : '');
        }
    });
    click.attachTo(plot);
    table.renderTo('#coverageChart');
}
/**
 * update chart to reflect new data
 */
function updateGraph() {
    xLabel.text(court_data[hash].short_name);
    currentData.data(chartData);
    table.redraw();
    updateTitle();
}
/**
 * hit the API to get new data
 */
function getData() {
   $.ajax({
       type: 'GET',
       url: '/api/rest/v3/coverage/' + hash + '/',
       success: function(data) {
           var entry = {},
               minYear = new Date().getFullYear(),
               count = 0;
           opinionCount = parseInt(data.total, 10);
           chartData = [];
           for (var item in data.annual_counts) {
               if (data.annual_counts.hasOwnProperty(item)) {
                   entry = {};
                   entry.x = parseInt(item, 10);
                   entry.y = data.annual_counts[item];
                   chartData.push(entry);
                   count += 1;
                   if (entry.x < minYear) {
                       minYear = entry.x;
                   }
               }
           }
           // Pad the data to have 7 values, else it looks horrible.
           while (chartData.length < 7) {
               chartData.push({x: --minYear, y: 0});
           }
           chartData.sort(function(a, b) {
               return a.x - b.x;
           });
           updateGraph();
       },
       error: function() {
           // need a better failure mode
           // If ajax fails (perhaps it's an invalid court?) set it back to all.
           window.location.hash = 'all';
       }
   });
}
/**
 * populate the court dropdown
 */
function addNavigation() {
    var options = [];
    $(sorted_courts).each(function(index, court) {
        options.push('<option value="' +
            court.pk + '" id="court_' +
            court.pk + '"">' +
            court.short_name +
            '</option>');
        // Make a totals dict (necessary, because otherwise courts are in a list
        // where we can't look things up by court name).
        court_data[court.pk] = {'pk': court.pk,
            'total': court.total_docs,
            'short_name': court.short_name};
    });
    $('#nav select').append(options.join(''));
    if (hash === '') {
        hash = 'all';
    }
    $('#nav select').val(hash)
        .chosen(); //trigger the "chosen" plugin
}
$('#nav select').change(function(){
    // Update the hash whenever the select is changed.
    var id = $('#nav select option:selected')[0].value;
    window.location.hash = id;
});
$(window).on('hashchange', function() {
    hash = window.location.hash.substr(1);
    hashCheck();
    getData();
});
$(document).ready(function() {
    addNavigation();
    hashCheck();
    drawGraph();
    $(window).trigger('hashchange');
    $('#nav select').chosen();  // Initialize the chosen drop down.
});
