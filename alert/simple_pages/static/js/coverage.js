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

    function getXDataValue(d) {
        return d.x;
    }

    function getYDataValue(d) {
        return d.y;
    }

    // Scales
    if (chartData.length > 10) {
        var xScale = new Plottable.Scale.Linear();
        var xAxis  = new Plottable.Axis.Numeric(xScale, 'bottom');
    } else {
        var xScale = new Plottable.Scale.Ordinal();
        var xAxis  = new Plottable.Axis.Category(xScale, 'bottom');
    }
    var yScale = new Plottable.Scale.Linear();

    // Plot Components
    var title  = new Plottable.Component.TitleLabel(parseInt(data.total, 10).toLocaleString() + ' Opinions');
    var yLabel = new Plottable.Component.Label('Number of Opinions', 'left');
    var xLabel = new Plottable.Component.Label(courtName);
    var yAxis  = new Plottable.Axis.Numeric(yScale, 'left');
    var plot   = new Plottable.Plot.Bar(xScale, yScale, true)
        .addDataset(chartData)
        .animate(true)
        .project("x", getXDataValue, xScale)
        .project("y", getYDataValue, yScale)
        .hoverMode('line') // need to do performance check on this setting or comment out
        .barLabelsEnabled(true);


    yAxis.formatter(function (d) {
        return d.toLocaleString();
    });

    var table = new Plottable.Component.Table([
        [null, null, title],
        [yLabel, yAxis, plot],
        [null, null, xAxis],
        [null, null, xLabel]
    ]);

    // Render it
    table.renderTo('#coverageChart');

    var hover = new Plottable.Interaction.Hover();
    hover.onHoverOver(function(hoverData) {
        var xString = hoverData.data[0].x;
        var yString = hoverData.data[0].y.toLocaleString();
        title.text(yString + " opinions in "+ xString);
    });
    hover.onHoverOut(function() {
        title.text(parseInt(data.total, 10).toLocaleString() + ' Opinions');
    });
    plot.registerInteraction(hover);

    var click = new Plottable.Interaction.Click();
    click.callback(function(p) {
        var bars = plot.getBars(p.x, p.y),
            year,
            prec = '',
            i;
        if (bars[0].length) {
            year = bars.data()[0].x;
            for (i = 0; i < precedentTypes.length; i++) {
                prec += '&' + precedentTypes[i] + '=on';
            }
            window.location.href = '/?type=o' +
                prec +
                '&filed_after=' + year +
                '-01-01&filed_before=' + (year + 1) +
                '-12-31&order_by=score+desc' + ((hash !== 'all') ? '&court=' + hash : '');
        }
    });
    plot.registerInteraction(click);
}

// Do this when the hash of the page changes (i.e. at page load or when a select is chosen.
$(window).hashchange(function() {
    hash = window.location.hash.substr(1);
    if (hash === '') {
        hash = 'all';
    } else if (document.getElementById(hash)){
        // The user tried to get to an unrelated ID
        hash = 'all';
    }
    $.ajax({
        type: 'GET',
        url: '/api/rest/v2/coverage/' + hash + '/',
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
    $(window).hashchange();
    $('#nav select').chosen();
});
