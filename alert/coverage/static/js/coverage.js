var line_chart_options = {
    gutter: 35,
    symbol: "circle",
    nostroke: false,
    smooth: true,
    shade: false,
    dash: "",
    axis: "0 0 1 1",
    axisxstep: 11, // How many x interval labels to render
    axisystep: 10
};

var canvas;
var court_data = new Array();

function addNavigation() {
    $(sorted_courts).each(function(index, court) {
        // Build up the sidebar
        var nav_link = $('<li></li>');
        $('<a></a>').attr('href', '#' + court.pk).attr('id', "court_" + court.pk)
            .text(court.short_name).appendTo(nav_link);
        if (index == 0) {
            nav_link.toggleClass('selected');
        }
        nav_link.appendTo('#nav ul');

        // Make a totals dict (necessary, because otherwise courts are in a list
        // where we can't look things up by court name).
        court_data[court.pk] = {'pk': court.pk,
                                'total': court.total_docs,
                                'short_name': court.short_name};
    });

    $(window).hashchange(function() {
        $('#nav li.selected').toggleClass('selected');
        $('#court_' + window.location.hash.substr(1)).parent().toggleClass('selected');

        // Clean things up
        canvas.clear();
        $('#graph svg').attr('height', '0');
        $('#graph table, #graph p').remove();

        // Update the drawing area
        var court_name = court_data[location.hash.substr(1)].pk;
        updateHeader(court_name);
        drawGraph(court_name);
    });
}

function updateHeader(court_id) {
    var s = court_data[court_id].short_name + ": " + data[court_id].total_docs + " opinions";
    $('#graph-header').text(s);
}

function drawGraph(court_id) {
    var keys = Object.keys(data[court_id]["years"]);
    keys.sort();
    var y = [];
    y.length = keys.length;
    $.each(data[court_id]["years"], function(key, value) {
      y[keys.indexOf(key)] = value;
    });
    var x = [];
    $.each(keys, function(index, value) {
      x.push(parseInt(value));
    });
    if (keys.length < 5) {
        // Make a table
        var not_enough_data = "<p>We do not have enough data to show this court as a graph. We require at least five year's data.</p>";
        $('#graph').append(not_enough_data);
        var table_stub = "<table><thead><tr><th>Year</th><th>Count</th></tr></thead><tbody></tbody></table>";
        $('#graph').append(table_stub);
        for(var i = 0; i < x.length; i++){
            $('#graph tbody').append('<tr><td>' + x[i] + '</td><td>' + y[i] + '</td></tr>');
        }
    } else {
        // Draw the full version
        $('#graph svg').attr('height', '400');
        var chart = canvas.linechart(40, 20, 680, 350, x, [y], line_chart_options).hover(function () {
            var color = this.symbol.attr("fill");
            var label = this.axis + ": " + this.value;
            this.popup = canvas.popup(this.x, this.y, label).insertBefore(this).attr([{stroke: color, fill: "#fff"}, { fill: "#000" }]);
        },
        function () {
            this.popup.remove();
        });
        chart.symbols.attr({r: 3});
        // X axis label
        var label_attrs = {'font-size': 14, 'font-weight': 'bold'};
        canvas.text(385, 385, court_data[court_id].short_name).attr(label_attrs);

        // Y axis label
        var y_label = canvas.text(15, 200, "Number of opinions").attr(label_attrs);
        y_label.transform('r-90');
    }
}

$(document).ready(function() {
    addNavigation();
    canvas = Raphael("graph", 710, 400);
    if (window.location.hash === ""){
        window.location.hash = 'all';
    }
    $(window).hashchange();
});
