/* global $, document, d3, Plottable*/

/*
For drawing the degrees of separation graph.
Given a set of citations in JSON
    and a DoS for the chart, as in don't show fourth for a third degree chart
sort them and pre-parse in order to build the network
    Degree of Separation starts at 1 not zero.
    opinions have a degree of separation ranging from endpoint
    connections have a degree of separation that is independent of the DoS of
    their endpoints

Look at using d3 maps and sets instead of some of the other datatypes:
    https://github.com/mbostock/d3/wiki/Arrays

create a chart with:
    aspect ratio, and have aspect ratio tied to vertical offset patterns
    max displayed Degrees of Separation
    an unlabeled y axis
        vertical spacing moving from math based to table selected
        oldest case low, newest case high to show building on foundation?
    a category x axis that contains times in order, but not a timeline
    grid
    legend
    scatterplot
        size by number of citations (not in graph, but total)
        color by degrees of separation
    a collection of line plots
        color by degrees of separation for that segment
below the plot add a table with:
    case name as link to case
    citation count
    date filed
 */

'use strict';

var citationJSON = {};

/**
 * [drawGraph description]
 * @param {string} target id of target HTML element to draw the chart in
 * @param {integer} maxDoS [description]
 * @param {string} aspect [description]
 * @return {object} [description]
 */
function drawGraph(target, maxDoS, aspect) {
    var workingJSON = [],
        parseDate = {}, // to parse dates in the JSON into d3 dates
        xDate = {}, // to format date for display
        xScale = {}, // the scaling function for x
        yScale = {}, // the scaling function for y
        sizeScale = {}, // the scale used to size the case circles
        colorScale = {}, // the scale used to keep the colors for the degrees of separation
        degrees = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'distant'],
        maxDegree = 0,
        xAxis = {}, // the x axis
        yAxis = {}, // the y axis
        xLabel = {}, // label for the x axis
        yLabel = {}, // label for the y axis
        legend = {}, // chart legend, in this case showing the different colors for degrees of separation
        xGrid = {},
        yGrid = {},
        grid = {},
        cases = {}, // reference to the case circles used to attach interactions
        connections = {}, // reference to the connection lines used to attach interactions
        plot = {}, // the plot area of the chart

        caseCount = 0, // number of opinions
        flagSize = 0, // square root of 2 less than the number of opinions

        distributions = [
            [1], // 1
            [1, 2], // 4
            [1, 2, 3], // 9
            [1, 3, 2, 4], // 16
            [2, 10, 5, 13, 16], // 25
            [1, 2, 3, 4, 5, 6], // 36
            [1, 2, 3, 4, 5, 6, 7], // 49
            [1, 2, 3, 4, 5, 6, 7, 8], // 64
            [1, 2, 3, 4, 5, 6, 7, 8, 9] // 81
            // how far does this table go?
        ],

        distribution = [], // will hold the correctly sized vertical distribution pattern

        links = {}, // used to hold DoS for connectors

        coords = {}, // object to hold extracted coordinates keyed by case id
        point = {}, // a point within coords

        JSONIndex = {},
        JSONCount = 0,

        caseHover = {}, // interaction behavior
        defaultCaseHoverText = '',
        caseHoverText = {}, // reference to the text in the object shown when hovering
        caseHoverGroup = {}, // reference to the hover show object
        caseClick = {}, // interaction behavior
        //connectionHover
        table = [], // holds the structure of the chart
        chart = {}; // the chart itself

    /**
     * [prepJSON description]
     */
    function prepJSON() {
        // sort by date_filed
        citationJSON.opinion_clusters.sort(function (a, b) {
            if (parseDate(a.date_filed) > parseDate(b.date_filed)) {
                return 1;
            }
            if (parseDate(a.date_filed) < parseDate(b.date_filed)) {
                return -1;
            }
            // a must be equal to b
            return 0;
        });
        // build index
        citationJSON.opinion_clusters.forEach(function (cluster) {
            point = {};
            point.num = JSONCount++;
            point.citedBy = [];
            JSONIndex[cluster.id] = point;
        });
        // add cited by others in JSON to each
        citationJSON.opinion_clusters.forEach(function (cluster) {
            cluster.sub_opinions[0].opinions_cited.forEach(function (item) {
                if (JSONIndex[item].citedBy.indexOf() === -1) {
                    JSONIndex[item].citedBy.push(cluster.id);
                }
            });
        });
    }

    function linkName(a, b) {
        var name = '';

        if (a < b) {
            name = a + ':' + b;
        } else {
            name = b + ':' + a;
        }
        return name;
    }

    /**
     * [traverse description]
     * @param {integer} nodeid index in JSON for current node
     * @param {integer} last previous node id
     * @param {integer} depth how far from newest case
     */
    function traverse(nodeid, last, depth) {
        var order = citationJSON.opinion_clusters[nodeid].travRev,
            linkId = '';

        if (nodeid !== last) {
            linkId = linkName(citationJSON.opinion_clusters[nodeid].id, citationJSON.opinion_clusters[last].id);
            if (links.hasOwnProperty(linkId)) {
                if (links[linkId].dr > depth) {
                    links[linkId].dr = depth;
                }
            } else {
                links[linkId] = {dr: depth};
            }
        }
        if (typeof order === 'undefined' || order > depth) {
            citationJSON.opinion_clusters[nodeid].travRev = depth;
            citationJSON.opinion_clusters[nodeid].sub_opinions[0].opinions_cited.forEach(function (item) {
                traverse(JSONIndex[item].num, nodeid, depth + 1);
            });
        }
    }

    /**
     * traverseBack
     * @param {integer} nodeid index in JSON for current node
     * @param {integer} last previous node id
     * @param {integer} depth how far from newest case
     */
    function traverseBack(nodeid, last, depth) {
        var order = citationJSON.opinion_clusters[nodeid].travFwd,
            linkId = '';

        if (nodeid !== last) {
            linkId = linkName(citationJSON.opinion_clusters[nodeid].id, citationJSON.opinion_clusters[last].id);
            if (links.hasOwnProperty(linkId)) {
                if (typeof links[linkId].df === 'undefined' || links[linkId].df > depth) {
                    links[linkId].df = depth;
                }
            }
        }
        if (typeof order === 'undefined' || order > depth) {
            citationJSON.opinion_clusters[nodeid].travFwd = depth;
            JSONIndex[citationJSON.opinion_clusters[nodeid].id].citedBy.forEach(function (item) {
                traverseBack(JSONIndex[item].num, nodeid, depth + 1);
            });
        }
    }

    /**
     * [calculateDoS description]
     */
    function calculateDoS() {
        var link = {},
            index = 1,
            thisDegree = 0;

        traverse(caseCount - 1, caseCount - 1, 0);
        traverseBack(0, 0, 0);

        citationJSON.opinion_clusters.forEach(function (cluster) {
            if (cluster.travFwd === 0 || cluster.travRev === 0) {
                cluster.order = 0;
            } else {
                cluster.order = cluster.travFwd + cluster.travRev - 1;
            }
            if (index === 1 || index === caseCount) {
                cluster.order = degrees[0];
            } else {
                thisDegree = cluster.order;
                if (thisDegree > degrees.length - 1) {
                    thisDegree = degrees.length;
                }
                if (thisDegree > maxDegree) {
                    maxDegree = thisDegree;
                }
                cluster.order = degrees[thisDegree];
            }
            cluster.count = index++;
        });
        for (link in links) {
            if (links.hasOwnProperty(link)) {
                thisDegree = links[link].dr + links[link].df - 2;
                if (thisDegree > maxDegree) {
                    maxDegree = thisDegree;
                }
                links[link].d = degrees[thisDegree]; // plus some math add bounds check refactor degree assign to function
            }
        }
    }

    function trimJSON(limit) {
        var max = parseInt(limit, 10),
            link = {};

        workingJSON = citationJSON.opinion_clusters.filter(function (cluster) {
            return degrees.indexOf(cluster.order) < max;
        });
        caseCount = workingJSON.length;
        for (link in links) {
            if (links.hasOwnProperty(link)) {
                if (degrees.indexOf(links[link].d) >= max) {
                    delete links[link];
                }
            }
        }
    }

    parseDate = d3.time.format('%Y-%m-%d').parse;
    xDate = d3.time.format('%b-%Y');

    prepJSON();

    caseCount = citationJSON.opinion_clusters.length;

    calculateDoS();

    trimJSON(maxDoS);

    flagSize = Math.ceil(Math.sqrt(caseCount));

    if (flagSize > 0 && flagSize < distributions.length) {
        distribution = distributions[flagSize - 1];
    } else {
        distribution = d3.range(1, flagSize + 2);
    }

    // hard code distributions for Friday
    // rewrite to use modulus and take aspect ratio into account
    distribution = [2, 10, 5, 13, 16];

    d3.select(target)
        .append('svg')
        .attr('id', 'coverageChart')
        .attr('height', '400px');

    xScale = new Plottable.Scales.Category(); // set switch for time or category time
    xScale.outerPadding(0.9);
    yScale = new Plottable.Scales.Category();
    yScale.domain(d3.range(1, d3.max(distribution) + 2).reverse());
    yScale.outerPadding(0.9);

    sizeScale = new Plottable.Scales.ModifiedLog();
    sizeScale.range([5, 50]);
    colorScale = new Plottable.Scales.Color();
    colorScale.domain(degrees.slice(0, maxDegree + 1));

    xAxis = new Plottable.Axes.Category(xScale, 'bottom');
    xAxis.tickLabelAngle(-90)
        .formatter(function (d) {
            return xDate(d);
        });

    yAxis = new Plottable.Axes.Category(yScale, 'left');
    // yAxis.formatter(function () {
    //     return '';
    // });

    xLabel = new Plottable.Components.AxisLabel('Time', 0);
    yLabel = new Plottable.Components.AxisLabel('Random', -90);

    legend = new Plottable.Components.Legend(colorScale).maxEntriesPerRow(4);

    xGrid = new Plottable.Scales.Linear()
        .domain([0, caseCount]);
        // .range([0, xAxis.width()]);
    yGrid = new Plottable.Scales.Linear()
        .domain([0, d3.max(distribution) + 2]);
        // .range([yAxis.height(), 0]);

    grid = new Plottable.Components.Gridlines(xGrid, yGrid);

    plot = new Plottable.Components.Group();
    plot.append(grid);

    cases = new Plottable.Plots.Scatter()
        .addDataset(new Plottable.Dataset(workingJSON))
        .addClass('caseScatter')
        .x(function (d) {
            return parseDate(d.date_filed);
        }, xScale)
        .y(function (d) {
            var value = 0;

            if (d.count === 1 || d.count === caseCount) {
                value = d3.max(distribution) + 1;
            } else {
                value = distribution[(d.count - 2) % flagSize];
            }
            return value;
        }, yScale)
        .size(function (d) {
            return d.citation_count;
        }, sizeScale)
        .attr('stroke', function (d) {
            return colorScale.scale(d.order);
        })
        .attr('fill', function (d) {
            return colorScale.scale(d.order);
        })
        .attr('title', function (d) {
            return d.case_name;
        });
    plot.append(cases);

    connections = new Plottable.Plots.Line()
        .x(function (d) {
            return parseDate(d.x);
        }, xScale)
        .y(function (d) {
            return d.y;
        }, yScale)
        .attr('stroke', function (d) {
            return colorScale.scale(d.c);
        })
        .attr('opacity', 0.5);
    plot.append(connections);

    workingJSON.forEach(function (cluster) {
        point = {};
        point.date_filed = cluster.date_filed;
        if (cluster.count === 1 || cluster.count === caseCount) {
            point.count = d3.max(distribution) + 1;
        } else {
            point.count = distribution[(cluster.count - 2) % flagSize];
        }
        point.order = cluster.order;
        coords[cluster.id] = point;
    });

    workingJSON.forEach(function (cluster) {
        cluster.sub_opinions[0].opinions_cited.forEach(function (id) {
            var name = linkName(cluster.id, id),
                color = 'unk';

            if (typeof links[name] !== 'undefined') {
                // replace the following if with the limiter to control greatest DoS connector shown
                if (typeof links[name].d !== 'undefined') {
                    color = links[name].d;
                }
                console.log(name, links[name]);
                connections.addDataset(new Plottable.Dataset([
                    {x: coords[cluster.id].date_filed, y: coords[cluster.id].count, c: color},
                    {x: coords[id].date_filed, y: coords[id].count, c: color}
                ]));
            }
        });
    });

    table = [
        [null, null, legend],
        [yLabel, yAxis, plot],
        [null, null, xAxis],
        [null, null, xLabel]
    ];

    chart = new Plottable.Components.Table(table);

    chart.renderTo('#coverageChart');

    caseHover = new Plottable.Interactions.Pointer();

    caseHoverGroup = cases
        .foreground()
        .append('g')
        .attr('transform', 'translate(0,0)')
        .style('visibility', 'hidden');
    caseHoverGroup
        .append('circle')
        .attr({
            'stroke': 'black',
            'fill': 'none',
            'r': 15,
            'cx': 0,
            'cy': 0
        });
    caseHoverText = caseHoverGroup
        .append('text')
        .attr('text-anchor', 'middle')
        .attr('transform', 'translate(0,-17)')
        .text(defaultCaseHoverText);

    caseHover.onPointerMove(function (p) {
        var datum = null,
            position = null,
            nearestEntity = null,
            cpd = null;

        if (typeof cases.entityNearest === 'function') {
            nearestEntity = cases.entityNearest(p);
            if (nearestEntity !== null) {
                datum = nearestEntity.datum;
                position = nearestEntity.position;
            }
        } else {
            cpd = cases.getClosestPlotData(p);
            if (cpd.data.length > 0) {
                datum = cpd.data[0];
                position = cpd.pixelPoints[0];
            }
        }
        if (datum !== null) {
            caseHoverText.text(datum.case_name_short);
            caseHoverGroup
                .attr('transform', 'translate(' + position.x + ',' + position.y + ')')
                .style('visibility', 'visible');
        } else {
            caseHoverText.text(defaultCaseHoverText);
            caseHoverGroup.style('visibility', 'hidden');
        }
    });
    caseHover.onPointerExit(function () {
        caseHoverText.text(defaultCaseHoverText);
        caseHoverGroup.style('visibility', 'hidden');
    });
    caseHover.attachTo(cases);

    caseClick = new Plottable.Interactions.Click();

    caseClick.onClick(function (c) {
        var datum = null,
            nearestEntity = null,
            cpd = null;

        if (typeof cases.entityNearest === 'function') {
            nearestEntity = cases.entityNearest(c);

            if (nearestEntity !== null) {
                datum = nearestEntity.datum;
            }
        } else {
            cpd = cases.getClosestPlotData(c);
            if (cpd.data.length > 0) {
                datum = cpd.data[0];
            }
        }
        if (datum !== null) {
            console.log(datum.absolute_url);
        }
    });

    caseClick.attachTo(cases);

    return workingJSON;

}

function citationTable(target, data, columns) {
    var table = d3.select(target).append('table'),
        thead = table.append('thead'),
        tbody = table.append('tbody'),
        rows = {};

    table.attr('class', 'table table-bordered table-hover');

    thead.append('tr')
        .selectAll('th')
        .data(columns)
        .enter()
        .append('th')
            .text(function (c) {
                return c.l;
            })
            .attr('class', 'info');

    rows = tbody.selectAll('tr')
        .data(data)
        .enter()
        .append('tr');

    rows.selectAll('td') // cells
        .data(function (row) {
            return columns.map(function (column) {
                return {
                    column: column.s,
                    value: row[column.s],
                    link: column.a,
                    format: column.f
                };
            });
        })
        .enter()
        .append('td')
        .html(function (d) {
            var html = '';

            if (typeof d.format === 'function') {
                html = d.format(d.value);
            } else {
                html = d.value;
            }
            if (typeof d.link !== 'undefined') {
                html = '<a href="' + d.link + '">' + html + '</a>';
            }
            return html;
        });

    return table;
}

$(document).ready(function () {
    var chartTarget = '#chart',
        tableTarget = '#table';

    function dateFormat(s) {
        var parseDate = d3.time.format('%Y-%m-%d').parse,
            format = d3.time.format('%b-%d-%Y');

        return format(parseDate(s));
    }

    /**
     * demonstrating additional formatting options
     * @param  {string} s value to format
     * @return {string} html formatted string
     */
    function bold(s) {
        return '<strong>' + s + '</strong>';
    }

    function trigger() {
        var used = {};

        var maxDoS = $('#degreesOfSeparationSelect').val(),
            aspect = $('#aspectRatioSelect').val();
        d3.select(chartTarget).select('svg').remove();
        d3.select(tableTarget).select('table').remove();
        citationJSON = JSON.parse(JSON.stringify(opinions));
        var used = drawGraph(chartTarget, maxDoS, aspect); // append target identifer to call
        citationTable(tableTarget, used,
            [
                {s: 'id', f: bold},
                {s: 'case_name_short', l: 'Case Name', a: 'absolute_url'},
                {s: 'citation_count', l: 'Total Citations'},
                {s: 'order', l: 'Degrees of Separation'},
                {s: 'date_filed', l: 'Date Filed', f: dateFormat}
            ]
        );
    }

    $('#degreesOfSeparationSelect').change(function () {
        trigger();
    });
    $('#aspectRatioSelect').change(function () {
        trigger();
    });
    trigger();
});
