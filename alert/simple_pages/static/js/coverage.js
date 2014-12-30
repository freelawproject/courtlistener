/*eslint-env browser */
/*global $, sorted_courts */

var hash = window.location.hash.substr(1),
    court_data = [],
    chartData = [];

function updateHeader(data) {
    $('#graph-header').text(data.total + ' Opinions');
}

function drawGraph(data) {
    chartData = [],
        entry = {},
        courtName = '';

    if (hash) {
        courtName = court_data[hash].short_name;
    }

    for (var item in data.annual_counts) {
        if (data.annual_counts.hasOwnProperty(item)) {
            entry = {};
            entry.x = item;
            entry.y = data.annual_counts[item];
            chartData.push(entry);
        }
    }
    chartData.sort(function(a, b) {
        return a.x - b.x;
    });

    if (chartData.length < 5) {
        $('#coverageChart').empty();
        new Chartographer.BarChart(chartData)
            .xLabel(courtName)
            .yLabel('Number of Opinions')
            .renderTo('#coverageChart');
    } else {
        $('#coverageChart').empty();
        new Chartographer.LineChart(chartData)
            .xLabel(courtName)
            .yLabel('Number of Opinions')
            .renderTo('#coverageChart');
    }
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
            updateHeader(data);
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

$(document).ready(function() {
    addNavigation();
    d3.select('#chart')
        .append('svg')
        .attr('id', 'coverageChart')
        .attr('height', '400px');
    $(window).hashchange();
    $('#nav select').chosen();
});
