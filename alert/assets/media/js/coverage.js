var graph_options = {
    gutter: 20,
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

function addNavigation() {
    $(courts).each(function(index, court) {
	var nav_link = $('<li></li>');
	$('<a href="#"></a>').attr('id', index).text(court.short_name).appendTo(nav_link);
	if (index == 0) {
	    nav_link.toggleClass('selected');
	}
	nav_link.appendTo('#nav ul');
    });
    
    $('#nav a').live('click', function() {
	$('#nav li.selected').toggleClass('selected');
	$(this).parent().toggleClass('selected');
	canvas.clear();
	drawGraph($(this).text());
    });
}

function drawGraph(court_name) {
    var keys = Object.keys(data[court_name]);
    keys.sort()
    var y = [];
    y.length = keys.length;
    $.each(data[court_name], function(key, value) {
      y[keys.indexOf(key)] = value;
    });
    x = [];
    $.each(keys, function(index, value) {
      x.push(parseInt(value));
    });

    var chart = canvas.linechart(40, 20, 650, 350, x, [y], graph_options).hover(function () {
	var color = this.symbol.attr("fill");
	var label = this.axis + ": " + this.value;
        this.popup = canvas.popup(this.x, this.y, label).insertBefore(this).attr([{stroke: color, fill: "#fff"}, { fill: "#000" }]);
    },  function () {
        this.popup.remove();
    });
    chart.symbols.attr({r: 3});

    // X axis label
    var label_attrs = {'font-size': 14, 'font-weight': 'bold'};
    canvas.text(385, 385, court_name).attr(label_attrs);

    // Y axis label
    var y_label = canvas.text(15, 200, "Number of opinions").attr(label_attrs);
    y_label.transform('r-90');
}

$(document).ready(function() {
    addNavigation();
    canvas = Raphael("graph", 710, 400);
    drawGraph('All Courts');
});