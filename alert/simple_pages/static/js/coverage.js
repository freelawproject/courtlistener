/*eslint-env browser */
/*global $, Raphael, sorted_courts */

var lineChartOptions = {
    gutter: 35,
    symbol: 'circle',
    nostroke: false,
    smooth: true,
    shade: false,
    dash: '',
    axis: '0 0 1 1',
    axisxstep: 11, // How many x interval labels to render
    axisystep: 10
};

var canvas;
var court_data = [];

function updateHeader(data) {
    $('#graph-header').text(data.total + ' Opinions');
}

function drawGraph(data) {
    var keys = Object.keys(data.annual_counts);
    keys.sort();
    var y = [];
    y.length = keys.length;
    $.each(data.annual_counts, function(key, value) {
        y[keys.indexOf(key)] = value;
    });
    var x = [];
    $.each(keys, function(index, value) {
        x.push(parseInt(value));
    });
    if (keys.length < 5) {
        // Make a table
        var notEnoughElements = '<p>We do not have enough data to show this court as a graph. We require at least five year\'s data.</p>';
        $('#graph').append(notEnoughElements);
        var tableStub = '<table class="table"><thead><tr><th>Year</th><th>Count</th></tr></thead><tbody></tbody></table>';
        $('#graph').append(tableStub);
        for(var i = 0; i < x.length; i++){
            $('#graph tbody').append('<tr><td>' + x[i] + '</td><td>' + y[i] + '</td></tr>');
        }
    } else {
        // Draw the full version
        $('#graph svg').attr('height', '100%');
        var chart = canvas.linechart(40, 0, 910, 370, x, [y], lineChartOptions)
            .hover(function () {
                var color = this.symbol.attr('fill');
                var label = this.axis + ': ' + this.value;
                this.popup = canvas.popup(this.x, this.y, label).insertBefore(this).attr([{stroke: color, fill: '#ffffff'}, { fill: '#000' }]);
            },
            function () {
                this.popup.remove();
            }
        );
        chart.symbols.attr({r: 3});
        // X axis label
        var labelAttributes = {'font-size': 14, 'font-weight': 'bold'};
        var courtName = court_data[location.hash.substr(1)].short_name;
        canvas.text(475, 370, courtName).attr(labelAttributes);

        // Y axis label
        var yLabel = canvas.text(15, 200, 'Number of Opinions').attr(labelAttributes);
        yLabel.transform('r-90');
    }
}

function addNavigation() {
    // Initialization....
    $(sorted_courts).each(function(index, court) {
        // Build up the chooser
        var selectElement = $('#nav select');
        $('<option></option>').attr('value', court.pk)
            .attr('id', 'court_' + court.pk)
            .text(court.short_name)
            .appendTo(selectElement);
        if (index === 0) {
            selectElement.toggleClass('selected');
        }
        selectElement.appendTo('#nav');

        // Make a totals dict (necessary, because otherwise courts are in a list
        // where we can't look things up by court name).
        court_data[court.pk] = {'pk': court.pk,
            'total': court.total_docs,
            'short_name': court.short_name};
    });

    // Do this when the hash of the page changes (i.e. at page load or when a select is chosen.
    $(window).hashchange(function() {
        var hash = window.location.hash.substr(1);
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
                // Clean things up
                canvas.clear();
                $('#graph svg').attr('height', '0');
                $('#graph table, #graph p').remove();

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

}

$(document).ready(function() {
    addNavigation();
    canvas = Raphael('graph', 950, 400);
    canvas.setViewBox(0, 0, 950, 400, true);
    canvas.setSize('100%', '100%');
    $(window).hashchange();
    $('#nav select').chosen();
});
