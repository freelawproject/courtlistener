/*eslint-env browser */
/*global $, sorted_courts, precedentTypes */

var hash = window.location.hash.substr(1),
    court_data = [],
    chartData = [];

function drawGraph(data) {
    var entry = {},
        courtName = court_data[hash].short_name;
    chartData = [];

    for (var item in data.annual_counts) {
        if (data.annual_counts.hasOwnProperty(item)) {
            entry = {};
            entry.x = parseInt(item, 10);
            entry.y = data.annual_counts[item];
            chartData.push(entry);
        }
    }
    chartData.sort(function(a, b) {
        return a.x - b.x;
    });
    $('#coverageChart').empty();

    // Scales
    var xScale, xAxis;
    if (chartData.length > 10) {
        xScale = new Plottable.Scales.Linear();
        xAxis  = new Plottable.Axes.Numeric(xScale, 'bottom');
    } else {
        xScale = new Plottable.Scales.Category();
        xAxis  = new Plottable.Axes.Category(xScale, 'bottom');
    }
    var yScale = new Plottable.Scales.Linear();

    // Plot Components
    var title  = new Plottable.Components.TitleLabel(
        parseInt(data.total, 10).toLocaleString() + ' Opinions');
    var yLabel = new Plottable.Components.Label('Number of Opinions')
        .angle(-90);
    var xLabel = new Plottable.Components.Label(courtName);
    var yAxis  = new Plottable.Axes.Numeric(yScale, 'left');
    var plot   = new Plottable.Plots.Bar()
        .addDataset(new Plottable.Dataset(chartData))
        .animated(true)
        .x(function(d) { return d.x}, xScale)
        .y(function(d) { return d.y}, yScale)
        .labelsEnabled(chartData.length <= 10);

    yAxis.formatter(function (d) {
        return d.toLocaleString();
    });

    var table = new Plottable.Components.Table([
        [null, null, title],
        [yLabel, yAxis, plot],
        [null, null, xAxis],
        [null, null, xLabel]
    ]);

    // Render it
    table.renderTo('#coverageChart');

    var pointer = new Plottable.Interactions.Pointer();
    pointer.onPointerMove(function(p){
        var entity = plot.entityNearest(p);
        var xString = entity.datum.x;
        var yString = entity.datum.y;
        title.text(yString + " opinions in " + xString);
    });
    pointer.onPointerExit(function(p) {
        title.text(parseInt(data.total, 10).toLocaleString() + ' Opinions');
    });
    pointer.attachTo(plot);

    var click = new Plottable.Interactions.Click();
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
}

// Do this when the hash of the page changes (i.e. at page load or when a select is chosen.
$(window).on('hashchange', function() {
    hash = window.location.hash.substr(1);
    if (hash === '') {
        hash = 'all';
    } else if (document.getElementById(hash)){
        // The user tried to get to an unrelated ID
        hash = 'all';
    }
    $.ajax({
        type: 'GET',
        url: '/api/rest/v3/coverage/' + hash + '/',
        success: function(data) {
            // Update the drawing area
            drawGraph(data);
        },
        error: function(){
            // If ajax fails (perhaps it's an invalid court?) set it back to all.
            window.location.hash = 'all';
        }
    });
});

$('#nav select').change(function(){
    // Update the hash whenever the select is changed.
    var id = $('#nav select option:selected')[0].value;
    window.location.hash = id;
});

function addNavigation() {
    $(sorted_courts).each(function(index, court) {
        // Build up the chooser
        var selectElement = $('#nav select');
        $('<option></option>').attr('value', court.pk)
            .attr('id', 'court_' + court.pk)
            .text(court.short_name)
            .appendTo(selectElement);
        selectElement.appendTo('#nav');

        // Make a totals dict (necessary, because otherwise courts are in a list
        // where we can't look things up by court name).
        court_data[court.pk] = {'pk': court.pk,
            'total': court.total_docs,
            'short_name': court.short_name};
    });
    if (hash === '') {
        hash = 'all';
    }
    $('#nav select').val(hash);
}

// hover
// click

$(document).ready(function() {
    addNavigation();
    d3.select('#chart')
        .append('svg')
        .attr('id', 'coverageChart')
        .attr('height', '400px');
    $(window).trigger('hashchange');
    $('#nav select').chosen();
});
