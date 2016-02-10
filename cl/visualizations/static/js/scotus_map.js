/* global $, document, d3, Plottable, embedUrl, opinions*/
'use strict';

/*
Look at using d3 maps and sets instead of some of the other datatypes:
	https://github.com/mbostock/d3/wiki/Arrays
 */

// rewrite the drawGraph call to use fewer parameters:
// opinions, settings {target, type, axis, height, DoS, mode}
// maybe target as first level param?

/**
 * [drawGraph description]
 * @param {string} target id of target HTML element to draw the chart in
 * @param {object} opinions the JSON object containing the data to work with
 * @param {string} chartType defaults to dos (Degrees of Separation), also [spaeth, genealogy]
 * @param {string} axisType controls X axis formatting as category or timeline
 * @param {string} height [description]
 * @param {integer} maxDoS a maximum degree of separation to show
 * @param {string} mode view or edit mode
 * @param {string} galleryId if in gallery mode is id of which chart to draw
 * @return {object} a new version of the source data containing only utilized information
 */
function drawGraph(target, opinions, chartType, axisType, height, maxDoS, mode, galleryId) {
	var workingJSON = JSON.parse(JSON.stringify(opinions)), // make a modifiable copy to retain original
		chartMode = (typeof chartType !== 'undefined') ? chartType : 'dos',
		xAxisMode = (typeof axisType !== 'undefined') ? axisType : 'cat',
		heightPx = height + 'px', // default, height is processed below
		parseDate = d3.time.format('%Y-%m-%d').parse, // to parse dates in the JSON into d3 dates
		xDate = d3.time.format('%b-%Y'), // to format date for display
		// data structures
		coords = {}, // object to hold extracted coordinates keyed by case id
		point = {}, // a point within coords
		links = {}, // used to hold DoS for connectors
		JSONIndex = {}, // a quick index to speed up data access
		caseCount = 0, // number of opinions
		maxDegree = 0, // the maximum degree of separation encountered
		label = '',
		//scales
		xScaleCat = {}, // the scaling function for x in category mode
		xCatPadding = 1, // padding in category mode to be added to right hand side
		xScaleTime = {}, // the scaling function for x in timeline mode
		yScale = {}, // the scaling function for y
		sizeScale = {}, // the scale used to size the case circles
		colorScale = {}, // the scale used to keep the colors for the degrees of separation
		//constants
		degrees = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'distant'],
		ddlu = ['N', 'C', 'L', 'U'], // from http://scdb.wustl.edu/documentation.php?var=decisionDirection
		ddlul = ['Neutral', 'Conservative', 'Liberal', 'Unspecifiable', 'Unknown'], // Decision Direction lookup long
		ddc = [0, 0, 0, 0, 0], // decision direction count encountered
		distribution = [], // will hold the correctly sized vertical distribution pattern
		offset = 0, // used for making 'random' y distribution
		spaethLabels = ['L5-4',
				'L6-3',
				'L7-2',
				'L8-1',
				'N9-0',
				'C8-1',
				'C7-2',
				'C6-3',
				'C5-4',
				'Unk'],
		index = 0,
		// chart parts
		chart = {}, // the chart itself
		table = [], // holds the structure of the chart
		legend = {}, // chart legend, in this case showing the different colors for degrees of separation
		yLabel = {}, // label for the y axis
		yAxis = {}, // the y axis
		plot = {}, // the plot area of the chart
		// parts of the plot
		xGrid = {},
		yGrid = {},
		grid = {},
		cases = {}, // reference to the case circles used to attach interactions
		connections = {}, // reference to the connection lines used to attach interactions
		// x axis
		xAxisCat = {}, // the x axis category
		xAxisTime = {}, // the x axis timeline
		// xLabel = {}, // label for the x axis
		// chart interactions
		caseHover = {}, // interaction behavior
		// defaultCaseHoverText = '',
		// caseHoverText = {}, // reference to the text in the object shown when hovering
		caseHoverGroup = {}, // reference to the hover show object
		caseClick = {}, // interaction behavior
		caseDrag = {}, // used in edit mode
		dragTarget = null;

	/**
	 * standardize the name structure for links to avoid duplication
	 * @param  {string} a case id
	 * @param  {string} b case id
	 * @return {string}   ordered case ids combined with lower first
	 */
	function linkName(a, b) {
		var name = '';

		if (a < b) {
			name = a + ':' + b;
		} else {
			name = b + ':' + a;
		}
		return name;
	}

	function setLabelAngle() {

		// console.log($(target).width() / caseCount);

		// change label angle when it gets too tight to read
		if ($(target).width() / caseCount < 56) {
			xAxisCat.tickLabelAngle(-90);
		} else {
			xAxisCat.tickLabelAngle(0);
		}
	}

	/**
	 * organization and indexing of the supplied JSON
	 */
	function prepJSON() {

		/**
		 * return a count of the citation object
		 * @param  {object} obj citation collection
		 * @return {integer}    the number of citations
		 */
		function citations(obj) {
			var size = 0,
				key = '';

			for (key in obj) {
				if (obj.hasOwnProperty(key)) {
					size++;
				}
			}
			return size;
		}

		// sort by date_filed, break ties so that opinion with no cites comes first
		workingJSON.opinion_clusters.sort(function (a, b) {
			if (parseDate(a.date_filed) > parseDate(b.date_filed)) {
				return 1;
			}
			if (parseDate(a.date_filed) < parseDate(b.date_filed)) {
				return -1;
			}
			// break the tie for two opinions on the same day, must start network with one with no cites
			if (citations(a.sub_opinions[0].opinions_cited) > citations(b.sub_opinions[0].opinions_cited)) {
				return 1;
			}
			if (citations(a.sub_opinions[0].opinions_cited) < citations(b.sub_opinions[0].opinions_cited)) {
				return -1;
			}
			return 0;
		});
		// build index
		workingJSON.opinion_clusters.forEach(function (cluster) {
			point = {};
			point.num = caseCount++;
			point.citedBy = [];
			JSONIndex[cluster.id] = point;
			// while iterating handle null values in JSON
			if (cluster.decision_direction === null) {
				cluster.decision_direction = '4';
			}
			if (cluster.votes_majority === null) {
				cluster.votes_majority = '-1';
			}
			if (cluster.votes_minority === null) {
				cluster.votes_minority = '-1';
			}
			// also count decision directions encountered (allows us to avoid showing unused labels)
			ddc[cluster.decision_direction]++;
		});
		// add cited by others in JSON to each
		workingJSON.opinion_clusters.forEach(function (cluster) {
			var item = '';

			for (item in cluster.sub_opinions[0].opinions_cited) {
				if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
					if (JSONIndex[item] && JSONIndex[item].citedBy.indexOf() === -1) {
						JSONIndex[item].citedBy.push(cluster.id);
					}
				}
			}
		});
	}

	/**
	 * [traverse description]
	 * @param {integer} nodeid index in JSON for current node
	 * @param {integer} last previous node id
	 * @param {integer} depth how far from newest case
	 */
	function traverse(nodeid, last, depth) {
		var order = workingJSON.opinion_clusters[nodeid].travRev,
			linkId = '',
			item = '';

		// for any iteration that is traversing between two points
		if (nodeid !== last) {
			linkId = linkName(workingJSON.opinion_clusters[nodeid].id, workingJSON.opinion_clusters[last].id);
			if (! links.hasOwnProperty(linkId)) {
				links[linkId] = {dr: depth};
			} else if (typeof links[linkId].dr === 'undefined' || links[linkId].dr > depth) {
				links[linkId].dr = depth;
			}
		}
		// branch and follow all children this direction
		if (typeof order === 'undefined' || order > depth) {
			// if this is our first time getting here or we found a shorter path
			workingJSON.opinion_clusters[nodeid].travRev = depth; // record the new shorter distance
			for (item in workingJSON.opinion_clusters[nodeid].sub_opinions[0].opinions_cited) {
				if (workingJSON.opinion_clusters[nodeid].sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
					traverse(JSONIndex[item].num, nodeid, depth + 1);
				}
			}
		}
	}

	/**
	 * traverseBack
	 * @param {integer} nodeid index in JSON for current node
	 * @param {integer} last previous node id
	 * @param {integer} depth how far from newest case
	 */
	function traverseBack(nodeid, last, depth) {
		var order = workingJSON.opinion_clusters[nodeid].travFwd,
			linkId = '';

		if (nodeid !== last) {
			linkId = linkName(workingJSON.opinion_clusters[nodeid].id, workingJSON.opinion_clusters[last].id);
			if (! links.hasOwnProperty(linkId)) {
				links[linkId] = {df: depth};
			} else if (typeof links[linkId].df === 'undefined' || links[linkId].df > depth) {
				links[linkId].df = depth;
			}
		}
		if (typeof order === 'undefined' || order > depth) {
			workingJSON.opinion_clusters[nodeid].travFwd = depth;
			JSONIndex[workingJSON.opinion_clusters[nodeid].id].citedBy.forEach(function (item) {
				traverseBack(JSONIndex[item].num, nodeid, depth + 1);
			});
		}
	}

	/**
	 * [calculateDoS description]
	 */
	function calculateDoS() {
		var link = {},
			i = 1,
			thisDegree = 0;

		traverse(caseCount - 1, caseCount - 1, 0);
		traverseBack(0, 0, 0);

		workingJSON.opinion_clusters.forEach(function (cluster) {
			if (cluster.travFwd === 0 || cluster.travRev === 0) {
				cluster.order = 0;
			} else {
				cluster.order = cluster.travFwd + cluster.travRev - 1;
			}
			if (i === 1 || i === caseCount) {
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
			cluster.count = i++;
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

	/**
	 * trim the workingJSON so that it includes cases that are under the DoS limit
	 * @param  {integer} limit [description]
	 */
	function trimJSON(limit) {
		var max = parseInt(limit, 10),
			link = {},
			c = 1;

		// filter out cases that have higher DoS
		workingJSON = workingJSON.opinion_clusters.filter(function (cluster) {
			return (chartType !== 'genealogy') ? degrees.indexOf(cluster.order) < max : true;
		});
		// renumber the remaining cases
		workingJSON.forEach(function (cluster) {
			cluster.count = c++;
		});
		// get the count of the remaining cases
		caseCount = c - 1;
		// remove links that have higher DoS
		if (chartType === 'dos') {
			for (link in links) {
				if (links.hasOwnProperty(link)) {
					if (degrees.indexOf(links[link].d) >= max) {
						delete links[link];
					}
				}
			}
		}
	}

	if (! $(target).length) { // if the target isn't on the page stop now
		return [];
	}

	// start of process
	prepJSON();

	// will get set to final in trimJSON
	caseCount = workingJSON.opinion_clusters.length;

	// calculate DoS for nodes and links
	calculateDoS();

	// now that DoS is calculated use that to remove distant nodes and links
	trimJSON(maxDoS);

	// cleaner to retain var for this and use it later on?
	d3.select(target)
		.append('svg')
		.attr('id', 'scotus-chart-' + galleryId)
		.attr('height', heightPx);

	// build vertical separation for dos chart
	if (chartType === 'dos') {
		distribution = [];
		distribution.push(50); // first at 50
		for (index = 0; index < caseCount - 2; index++) {
			// need better numbers here
			offset += [68, 77, 55, 37, 42, 21, 62][index % 7];
			distribution.push((offset % 91) + 5);
		}
		distribution.push(50); // last at 50
	}

	/**
	 * if we have a set y value use it, otherwise use the distribution
	 * this allows us to respect edits and untangle the DoS network
	 * @param  {object} d case
	 * @return {integer}   the vertical distribution for that case
	 */
	function dosYSpread(d) {
		return (d.y) ? d.y : distribution[d.count - 1];
	}

	/**
	 * [spaethYSpread description]
	 * @param  {object} d case
	 * @return {integer}   the vertical distribution for that case
	 */
	function spaethYSpread(d) {
		var minority = d.votes_minority,
			majority = String(9 - Number(minority)), // d.votes_majority,
			decision_direction = ddlu[d.decision_direction],
			prefix = (majority === '9') ? 'N' : decision_direction,
			value = '';

		if (minority === '-1') {
			value = 'Unk';
		} else {
			value = prefix + majority + '-' + minority;
		}
		return value;
	}

	xScaleCat = new Plottable.Scales.Category(); // set switch for time or category time
	xScaleCat.outerPadding(0.9);
	// ensure correct order by loading dates in
	// preloading these allows us to draw connections before drawing nodes
	xScaleCat.domain(workingJSON.map(function (d) {
		return parseDate(d.date_filed);
	}));

	// the rangeBand is the percent of the width of the chart that a single data point takes up
	// the floor of 5 div this div 100 yeilds a number from 0 to x that can be used to add padding

	if (galleryId === '') {
		while (Math.floor(5 / xScaleCat.rangeBand() / 100) > xCatPadding && xCatPadding < 5) {
			xScaleCat.domain(d3.merge([xScaleCat.domain(), [parseDate('9999-01-0' + xCatPadding.toString())]]));
			xCatPadding++;
		}
	}

	xScaleTime = new Plottable.Scales.Time();
	yScale = new Plottable.Scales.Category();
	yAxis = new Plottable.Axes.Category(yScale, 'left');

	if (chartMode === 'dos') {
		yScale.domain(d3.range(0, 100));
		yAxis.innerTickLength(0)
			.endTickLength(0)
			.formatter(function () {
				return '';
			})
			.tickLabelPadding(0);
	} else {
		if (ddc[3] === 0 && ddc[4] === 0) { // there are no unknown or unspecifiable
			spaethLabels.pop(); // get rid of 'Unk'
		}
		yScale.domain(spaethLabels);
		yAxis.formatter(function (d) {
			var value = d;

			if (value !== 'Unk') {
				value = value.slice(1); // remove leading letter
			}
			return value;
		});
	}

	yScale.outerPadding(0.9);
	sizeScale = new Plottable.Scales.Linear();
	sizeScale.range([10, Math.max(10, height / 12)]);
	colorScale = new Plottable.Scales.Color();

	/**
	 * [filter description]
	 * @param  {array} source  [description]
	 * @param  {array} compare [description]
	 * @return {array}         [description]
	 */
	function filter(source, compare) {
		var array = [],
			i = 0,
			sl = source.length,
			cl = compare.length;

		for (i = 0; i < sl; i++) {
			if (i < cl && compare[i] > 0) {
				array.push(source[i]);
			}
		}
		return array;
	}

	if (chartMode === 'dos') {
		colorScale.domain(degrees.slice(0, d3.min([maxDoS, maxDegree + 1])));
	} else {
		colorScale.domain(filter(ddlul, ddc));
		colorScale.range(filter([
			'purple',
			'red',
			'blue',
			'green',
			'orange'
		], ddc));
	}

	xAxisCat = new Plottable.Axes.Category(xScaleCat, 'bottom');

	xAxisCat.formatter(function (d) {
		var result = xDate(d);

		if (d > new Date('9998-01-01')) {
			result = '';
		}
		return result;
	});
	xAxisTime = new Plottable.Axes.Time(xScaleTime, 'bottom');
	xAxisTime.formatter(function (d) {
		return xDate(d);
	});

	setLabelAngle();

	label = (chartMode === 'dos') ? 'Random' : 'Conservative  ⟵  ⟶  Liberal';

	yLabel = new Plottable.Components.AxisLabel(label, -90);

	legend = new Plottable.Components.Legend(colorScale).maxEntriesPerRow(5);

	if (xAxisMode === 'cat') {
		xGrid = new Plottable.Scales.Linear()
			.domain([0, caseCount])
			.tickGenerator(function () {
				return d3.range(0, caseCount + 1, 1);
			});
	} else {
		xGrid = xScaleTime;
	}

	yGrid = new Plottable.Scales.Linear();
	if (chartMode === 'dos') {
		yGrid.domain([0, 100])
			.tickGenerator(function () {
				return [0, 100];
			}); // handle dos and non dos

	} else if (ddc[3] > 0 || ddc[4] > 0) { // there is an 'Unk' category
		yGrid.domain([0, 11]);
	} else {
		yGrid.domain([0, 10]);
	}

	plot = new Plottable.Components.Group();

	grid = new Plottable.Components.Gridlines(xGrid, yGrid);

	plot.append(grid);

	connections = new Plottable.Plots.Line()
		.x(function (d) {
			return parseDate(d.x);
		}, (xAxisMode === 'cat') ? xScaleCat : xScaleTime)
		.y(function (d) {
			return d.y;
		}, yScale)
		.attr('stroke', function (d) {
			return colorScale.scale(d.c);
		})
		.attr('opacity', function (d) {
			return d.o * ((chartType !== 'genealogy') ? 0.5 : 0.9); // drop all by a percent
		});
	plot.append(connections);

	/**
	 * Scales objects such that it treats the last differently
	 * in order to make most recent case visible when it has no citations
	 * @param  {object} cites where to extract citation_count
	 * @param  {integer} i  which number is this?
	 * @return {integer}    area adjusted value
	 */
	function scalePlot(cites, i) {
		var value = 0,
			domain = [];

		if (i === caseCount - 1 && cites === 0) {
			domain = sizeScale.domain();
			value = (domain[0] + domain[1]) / 2; // set the most recent case size to half
		} else {
			value = cites;
		}
		return Math.sqrt(value / Math.PI);
	}

	cases = new Plottable.Plots.Scatter()
		.addDataset(new Plottable.Dataset(workingJSON))
		.addClass('caseScatter')
		.x(function (d) {
			return parseDate(d.date_filed);
		}, (xAxisMode === 'cat') ? xScaleCat : xScaleTime)
		.y(function (d) {
			return (chartMode === 'dos') ? dosYSpread(d) : spaethYSpread(d);
		}, yScale)
		.size(function (d, i) {
			return scalePlot(d.citation_count, i);
		}, sizeScale)
		.attr('stroke', function (d) {
			return colorScale.scale((chartMode === 'dos') ? d.order : ddlul[d.decision_direction]);
		})
		.attr('fill', function (d) {
			return colorScale.scale((chartMode === 'dos') ? d.order : ddlul[d.decision_direction]);
		})
		.attr('opacity', 1);
	if (galleryId === '') {
		cases.labelsEnabled(function () {
			return true;
		})
		.label(function (d) {
			return (d.case_name_short) ? d.case_name_short : d.case_name; //.split(' ')[0]
		});
	}
	plot.append(cases);

	/**
	 * [calcConnections description]
	 */
	function calcConnections() {
		// empty any old data
		connections.datasets().forEach(function (set) {
			connections.removeDataset(set);
		});
		// generate index
		workingJSON.forEach(function (cluster) {
			point = {};
			point.date_filed = cluster.date_filed;
			point.count = dosYSpread(cluster);
			point.order = cluster.order;
			coords[cluster.id] = point;
		});
		// build new connections
		workingJSON.forEach(function (cluster) {
			var item = '',
				name = '',
				color = '',
				opacity = 0;

			for (item in cluster.sub_opinions[0].opinions_cited) {
				if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
					name = linkName(cluster.id, item);
					color = 'unk';
					opacity = cluster.sub_opinions[0].opinions_cited[item].opacity;
					if (typeof opacity === 'undefined') {
						opacity = 1;
					}
					if (typeof links[name] !== 'undefined') {
						// replace the following if with the limiter to control greatest DoS connector shown
						if (typeof links[name].d !== 'undefined') {
							color = links[name].d;
						}
						connections.addDataset(new Plottable.Dataset([
							{x: coords[cluster.id].date_filed, y: coords[cluster.id].count, c: color, o: opacity},
							{x: coords[item].date_filed, y: coords[item].count, c: color, o: opacity}
						]));
					}
				}
			}
		});
	}

	if (chartMode === 'dos') {
		calcConnections();
	} else {
		if (chartMode === 'genealogy') {

/*
1.	Start with all of the cases from the bacon map and sort them in chronological order.

2.	Starting with the most recent case and working your way back to the oldest case:

3.	Get all citations from that case, and find the most recent cited-case that (a) has the same decision direction
	(conservative/liberal) and (b) is also in the set of cases from the bacon map. Note that the found citation may
	be one that is displayed on the bacon map, but it may also be one that was excluded from the bacon map (because
	it would have resulted in too many connections between the start and end cases). If you find a citation, add it
	to the genealogy map and skip to step (6).

4.	If you do not find a citation in step (3) above, then get all citations from that case, and find the most
	recent cited-case that is also in the set of cases from the bacon map, regardless of the decision direction.
	Again, this may be a citation that was not displayed on the bacon map.  If you find a citation, then add it to
	the genealogy map and skip step (5).

5.	If you are starting with a group of cases from a bacon map, you should never get to this step.  However, to
	make this algorithm work with other groups of cases, you will reach this step if there are no citations from
	this case to any other ones in the original group of cases.  If this occurs, then instead of checking the
	cases that this one cites, check to see if this case is cited-by another case in the set.  Give preference to
	one with the same decision direction that is also closest in age.  If one with the same decision direction
	cannot be found, then just fine the one that is the closest in age and add that citation to the genealogy map.

6.	Repeat steps 3-5 for the rest of the cases in the set, continuing backwards chronologically through the cases.

7.	Add the citations to the appropriate strands (conservative/liberal/unknown) based on the decision direction of
	the citing case.
*/

			workingJSON.forEach(function (cluster) {
				var item = {},
					recent = parseDate('1500-01-01'),
					recentIndex = 0,
					recentOp = parseDate('1500-01-01'),
					recentOpIndex = 0;

				for (item in cluster.sub_opinions[0].opinions_cited) {
					if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
						cluster.sub_opinions[0].opinions_cited[item].opacity = 0.15;
						if (typeof workingJSON[JSONIndex[item].num] !== 'undefined') {
							if (cluster.decision_direction === workingJSON[JSONIndex[item].num].decision_direction) {
								if (recent < parseDate(workingJSON[JSONIndex[item].num].date_filed)) {
									recent = parseDate(workingJSON[JSONIndex[item].num].date_filed);
									recentIndex = item;
								}
							} else if (recentOp < parseDate(workingJSON[JSONIndex[item].num].date_filed)) {
								recentOp = parseDate(workingJSON[JSONIndex[item].num].date_filed);
								recentOpIndex = item;
							}
						}
					}
				}
				if (recentIndex !== 0) {
					cluster.sub_opinions[0].opinions_cited[recentIndex].opacity = 1;
					workingJSON[JSONIndex[recentIndex].num].visited = true;
				}
				// end case may not be able to branch to op direction?
				if ((recentOpIndex !== 0 && recentIndex === 0) || cluster.count === caseCount && recentOpIndex !== 0) {
					cluster.sub_opinions[0].opinions_cited[recentOpIndex].opacity = 1;
					workingJSON[JSONIndex[recentOpIndex].num].visited = true;
				}
			});
			// second pass to pick up orphans
			workingJSON.forEach(function (cluster) {
				var item = {};

				for (item in cluster.sub_opinions[0].opinions_cited) {
					if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
						if (! workingJSON[JSONIndex[item].num].hasOwnProperty('visited') &&
							cluster.decision_direction === workingJSON[JSONIndex[item].num].decision_direction) {
							cluster.sub_opinions[0].opinions_cited[item].opacity = 1;
							workingJSON[JSONIndex[item].num].visited = true;
						}
					}
				}
				for (item in cluster.sub_opinions[0].opinions_cited) {
					if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
						if (! workingJSON[JSONIndex[item].num].hasOwnProperty('visited')) {
							cluster.sub_opinions[0].opinions_cited[item].opacity = 1;
							workingJSON[JSONIndex[item].num].visited = true;
						}
					}
				}
			});
		}
		// spaeth and genealogy
		workingJSON.forEach(function (cluster) {
			var minority = cluster.votes_minority,
				majority = String(9 - parseInt(minority, 10)),
				decision_direction = ddlu[cluster.decision_direction],
				prefix = (majority === '9') ? 'N' : decision_direction;

			point = {};
			point.date_filed = cluster.date_filed;
			if (minority === '-1') {
				point.split = 'Unk';
				point.dec = 'Unknown';
			} else {
				point.split = prefix + majority + '-' + minority;
				point.dec = ddlul[cluster.decision_direction];
			}
			coords[cluster.id] = point;
		});
		workingJSON.forEach(function (cluster) {
			var item = {},
				opacity = 0;

			for (item in cluster.sub_opinions[0].opinions_cited) {
				if (cluster.sub_opinions[0].opinions_cited.hasOwnProperty(item)) {
					opacity = cluster.sub_opinions[0].opinions_cited[item].opacity;
					if (typeof opacity === 'undefined') {
						opacity = 1;
					}
					// badly formed data can result in coords[item] being undefined, check for this
					if (typeof coords[item] !== 'undefined') {
						connections.addDataset(new Plottable.Dataset([
							{x: coords[cluster.id].date_filed, y: coords[cluster.id].split, c: coords[item].dec, o: opacity},
							{x: coords[item].date_filed, y: coords[item].split, c: coords[item].dec, o: opacity}
						]));
					}
				}
			}
		});
	}

	// if we are not in gallery mode
	if (galleryId === '') {
		table = [
			[null, null, legend, null],
			[yLabel, yAxis, plot, null],
			[null, null, (xAxisMode === 'cat') ? xAxisCat : xAxisTime, null]//,
			// [null, null, xLabel, null]
		];
	} else if (chartType === 'dos') { // gallery dos mode
		table = [[plot]];
	} else { // gallery spaeth and genealogy mode
		table = [[yLabel, yAxis, plot]];
	}

	chart = new Plottable.Components.Table(table);

	chart.renderTo('#scotus-chart-' + galleryId);

	window.addEventListener('resize', function () {
		setLabelAngle();
		chart.redraw();
	});

	if (galleryId === '') {

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
		// caseHoverText = caseHoverGroup
		// 	.append('text')
		// 	.attr('text-anchor', 'middle')
		// 	.attr('transform', 'translate(0,0)')
		// 	.text(defaultCaseHoverText);

		caseHover.onPointerMove(function (p) {
			var datum = null,
				position = null,
				nearestEntity = null,
				cpd = null;

			if (typeof cases.entityNearest === 'function') {
				nearestEntity = cases.entityNearest(p);
				if (typeof nearestEntity !== 'undefined') {
					if (nearestEntity !== null) {
						datum = nearestEntity.datum;
						position = nearestEntity.position;
					}
				}
			} else {
				cpd = cases.getClosestPlotData(p);
				if (cpd.data.length > 0) {
					datum = cpd.data[0];
					position = cpd.pixelPoints[0];
				}
			}
			if (datum !== null) {
				// caseHoverText.text(datum.case_name_short);
				caseHoverGroup
					.attr('transform', 'translate(' + position.x + ',' + position.y + ')')
					.style('visibility', 'visible')
					.select('circle')
					.attr('r', sizeScale.scale(scalePlot(datum.citation_count, datum.count - 1)) / 2);
			} else {
				// caseHoverText.text(defaultCaseHoverText);
				caseHoverGroup.style('visibility', 'hidden');
			}
		});
		caseHover.onPointerExit(function () {
			// caseHoverText.text(defaultCaseHoverText);
			caseHoverGroup.style('visibility', 'hidden');
		});

		if (mode === 'view' && galleryId === '') {
			caseHover.attachTo(cases);
			caseClick = new Plottable.Interactions.Click();
			caseClick.onClick(function (c) {
				var entity = cases.entitiesAt(c)[0];

				if (entity) {
					window.open('https://www.courtlistener.com' + entity.datum.absolute_url, '_blank');
				}
			});
			caseClick.attachTo(cases);
		}

		if (mode === 'edit' && chartType === 'dos') {
			caseDrag = new Plottable.Interactions.Drag();

			caseDrag.onDragStart(function (c) {
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
					dragTarget = datum;
				}
			});

	// http://plottablejs.org/examples/datasets/
	// http://plottablejs.org/examples/spacerace/

			caseDrag.onDrag(function (c, b) {
				// console.log(b.y, Math.round(100 * b.y / cases.height(), 0));
				dragTarget.y = Math.round(100 * b.y / cases.height(), 0);
				cases.redraw();
			});

			caseDrag.onDragEnd(function (c, b) {
				// console.log('end', 100 * b.y / cases.height(), dragTarget.case_name_short);
				dragTarget.y = Math.round(100 * b.y / cases.height(), 0);
				calcConnections();
				chart.redraw();
			});

			caseDrag.attachTo(cases);
		}
	}
	// the following bit of extremely odd looking code is in place to counter
	// a behavior seen with IE when it is used in place on the production system
	// that does not appear in dev. The bug causes in IE portions of the chart to
	// not be visible.
	$('svg').css('line-height', $('svg').css('line-height'));
	return workingJSON;
}

/**
 * [citationTable description]
 * @param  {string} target  [description]
 * @param  {object} data    [description]
 * @param  {array} columns [description]
 * @returns {string} [description]
 */
function citationTable(target, data, columns) {
	var table = d3.select(target).append('div').attr('class', 'table-responsive').append('table'),
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
			.attr('class', 'info')
			.style('cursor', 'pointer')
			.on('click', function (d) {
				if (typeof d.d === 'undefined') {
					d.d = 'a';
				}
				table.selectAll('tbody tr')
					.sort(function (a, b) {
						var direction = '';

						if (d.d === 'a') {
							direction = d3.ascending(a[d.s], b[d.s]);
						} else {
							direction = d3.descending(a[d.s], b[d.s]);
						}
						return direction;
					});
				table.selectAll('thead th')
					.html(function (c) {
						var label = c.l;

						if (c.s === d.s) {
							if (d.d === 'a') {
								label += ' <i class="fa fa-caret-up" aria-hidden="true"></i>';
								d.d = 'd';
							} else {
								label += ' <i class="fa fa-caret-down" aria-hidden="true"></i>';
								d.d = 'a';
							}
						}
						return label;
					});
			});

	rows = tbody.selectAll('tr')
		.data(data)
		.enter()
		.append('tr');

	rows.selectAll('td') // cells
		.data(function (row) {
			var val = '';

			return columns.map(function (column) {
				if ($.isArray(column.s)) {
					val = [];
					column.s.forEach(function (i) {
						val.push(row[i]);
					});
				} else {
					val = row[column.s];
				}
				return {
					column: column.s,
					value: val,
					link: row[column.a],
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

/**
 * [degreeOfDissent description]
 * @param  {object} cases [description]
 * @return {object}       containing degree of dissent, number of cases used, and total number of cases
 */
function degreeOfDissent(cases) {
	var dods = [];

	cases.forEach(function (c) {
		var minority = c.votes_minority;

		if (minority.toString() !== '-1') {
			dods.push(minority * 0.25);
		}
	});

	return {'d': (d3.sum(dods) / dods.length),
		'c': dods.length,
		'l': cases.length};
}

/**
 * [attachDoDInfo description]
 * @param  {string} target  [description]
 * @param  {object} dissent [description]
 */
function attachDoDInfo(target, dissent) {
	d3.select(target)
		.text(dissent.d.toFixed(2) +
			' for ' + dissent.c +
			' cases of ' + dissent.l);
}

/**
 * [casesMetadata description]
 * @param  {[type]} data   [description]
 */
function casesMetadata(data) {
	var dodInfo = '#dod-info',
		dodMeter = d3.select('#dod-chart'),
		meter = '',
		dissent = 0,
		i = 0;

	if (data.length) { // if there are cases
		dissent = degreeOfDissent(data);

		attachDoDInfo(dodInfo, dissent);

		dodMeter.html('');

		meter = dodMeter.append('svg')
			.attr('height', 40)
			.append('g')
			.attr('stroke', 'black')
			.attr('font-family', 'Arial')
			.attr('font-size', 12)
			.attr('text-anchor', 'middle');

		meter.append('line') // base
			.attr('x1', 10)
			.attr('y1', 20)
			.attr('x2', 110)
			.attr('y2', 20);

		for (i = 0; i < 5; i++) {
			meter.append('line')
				.attr('x1', (i * 25) + 10)
				.attr('y1', 20)
				.attr('x2', (i * 25) + 10)
				.attr('y2', 11);
			meter.append('text')
				.attr('x', (i * 25) + 10)
				.attr('y', 35)
				.text((9 - i) + '-' + i);
		}

		meter.append('text')
				.attr('x', 10)
				.attr('y', 9)
				.text('0');
		meter.append('text')
				.attr('x', 109)
				.attr('y', 9)
				.text('1');

		meter.append('path')
			.attr('fill', 'red')
			.attr('d', 'M' + ((dissent.d * 100) + 10) + ' 18 l -10 -10 l 20 0 z');
	}
}

/**
 * [description]
 */
$(document).ready(function () {
	var settings = {
			'type': 'dos',
			'xaxis': 'cat',
			'dos': 3,
			'mode': 'view'
		},
		args = {},
		chartTarget = '#chart',
		tableTarget = '#case-table',
		caseCountTarget = '#case-count',
		item = {},
		used = {},
		dissent = {},
		height = 0,
		type = '';

	// Read a page's GET URL variables and return them as an associative array.
	function getUrlVars() {
		var vars = {},
			i = 0,
			hash = '',
			hashes = window.location.href.slice(window.location.href.indexOf('?') + 1).split('&');

		for (i = 0; i < hashes.length; i++) {
			hash = hashes[i].split('=');
			vars[hash[0]] = hash[1];
		}
		return vars;
	}

	function updateUrl(payload) {
		var newUrl = window.location.href.split('?')[0],
			params = '',
			key = '',
			count = 0,
			embedPre = '<iframe height="500" width="560" src="',
			embedPost = '" frameborder="0" allowfullscreen></iframe>';

		for (key in payload) {
			if (payload.hasOwnProperty(key) && key !== 'mode') {
				params += ((count === 0) ? '?' : '&') + key + '=' + payload[key];
				count++;
			}
		}

		if ($('#embed-input').length) {
			$('#embed-input').val(embedPre + embedUrl + params + embedPost);
		}

		// console.log('newUrl', newUrl, count, payload);
		window.history.replaceState({}, '', newUrl + params);
	}

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
	// function bold(s) {
	// 	return '<strong>' + s + '</strong>';
	// }

	function formatSplit(s) {
		var r = 'no data';

		// filter out nulls and out of bound numbers
		if (s[0].toString() !== '-1' || s[1].toString() !== '-1') {
			r = s[0] + '-' + s[1];
		}
		return r;
	}

	function formatDecision(s) {
		var dec = ['Neutral', 'Conservative', 'Liberal', 'Unspecifiable', 'Unknown'],
			r = 'no data';

		// filter out nulls and out of bound numbers
		if (s && s >= 0 && s <= 4) {
			r = dec[s];
		}
		return r;
	}

	function scdbLink(s) {
		var value = 'no data';

		if (s !== '') {
			value = '<a href="http://supremecourtdatabase.org/analysisCaseDetail.php?cid=' +
				s + '" target="_blank">' + s + '</a>' +
				'&nbsp;<i class="gray fa fa-external-link"></i>';
		}
		return value;
	}

	/**
	 * [setHeight description]
	 * @param {string} target [description]
	 * @param {boolean} full   [description]
	 * @returns {integer} [description]
	 */
	function setHeight(target, full) {
		var h = 0,
			v = 0,
			w = 0;

		v = $(target).data('height');
		if (typeof v !== 'undefined') {
			// if data is set on target then use data-height
			h = v;
		} else if (typeof settings.height !== 'undefined') {
			// if url settings contain height use that
			h = settings.height;
		}
		// if height is either 'fullscreen' or in ratio format
		if (h === 'screen') {
			h = $(window).height();
		}
		if (typeof h === 'string' && h.indexOf(':') !== -1) {
			w = $(target).width();
			h = (w / h.split(':')[0]) * h.split(':')[1];
		}
		if (h === 0) {
			// if none of these use defaults based on full
			h = (full) ? 600 : 300;
		}
		return h;
	}

	/**
	 * [trigger description]
	 * @param  {object} params [description]
	 */
	function trigger(params) {
		var chartType = params.type,
			axisType = params.xaxis,
			maxDoS = params.dos;

		height = setHeight(chartTarget, true);
		// type = chartType [spread, spaeth, gene]
		// xaxis = axisType [cat, time]
		// dos = maxDos [integer 1->]
		d3.select(chartTarget).select('svg').remove();
		d3.select(tableTarget).select('table').remove();

			// drawGraph (
			// 	target -- where to draw it
			// 	type -- which type or default to DoS 'dos', 'spaeth', 'genealogy'
			// 	xAxis type -- timeline or time category 'time' or 'cat'
			// 	height -- how tall to make it instead of aspect ratio
			// 	maxDoS -- maximum degree of separation to show, is this only DoS
			// )

		used = drawGraph(chartTarget, opinions, chartType, axisType, height, maxDoS, params.mode, '');
		$(caseCountTarget).text(used.length);
		citationTable(tableTarget, used,
			[
				// {s: 'source', }
				// {s: 'id', f: bold},
				// {s: 'order', l: 'Degrees of Separation'},
				{s: 'case_name', l: 'Case Name', a: 'absolute_url'},
				{s: 'scdb_id', l: 'SCDB', f: scdbLink},
				{s: 'citation_count', l: 'Total Citations'},
				{s: 'date_filed', l: 'Date Filed', f: dateFormat},
				{s: ['votes_majority', 'votes_minority'], l: 'Vote Count', f: formatSplit},
				{s: 'decision_direction', l: 'Direction', f: formatDecision}
				// {s: '', l: 'Spaeth Issue'},
				// {s: '', l: 'Issue Area'},
				// {s: '', l: 'Provision'}
			]
		);
		casesMetadata(used);
	}

	// get url search parameters
	args = getUrlVars();

	// merge settings and args
	$.extend(settings, args);

	function setDosEnable() {
		if (settings.type === 'genealogy') {
			$('#degreesOfSeparationSelect').prop('disabled', true);
		} else {
			$('#degreesOfSeparationSelect').prop('disabled', false);
		}
	}
	setDosEnable();

	if (opinions.hasOwnProperty('opinion_clusters')) {
		// do one
		$('#chartTypeSelect').val(settings.type);
		$('#axisTypeSelect').val(settings.xaxis);
		$('#heightTypeSelect').val(settings.height);
		$('#degreesOfSeparationSelect').val(settings.dos);

		// unwrap dataSourceSelect for courtlistener
		// on select JSON in the data and then call drawGraph()
		$('#chartTypeSelect').change(function () {
			settings.type = $('#chartTypeSelect').val();
			setDosEnable();
			updateUrl(settings);
			trigger(settings);
		});
		$('#axisTypeSelect').change(function () {
			settings.xaxis = $('#axisTypeSelect').val();
			updateUrl(settings);
			trigger(settings);
		});
		$('#heightTypeSelect').change(function () {
			settings.height = $('#heightTypeSelect').val();
			updateUrl(settings);
			trigger(settings);
		});
		$('#degreesOfSeparationSelect').change(function () {
			settings.dos = $('#degreesOfSeparationSelect').val();
			updateUrl(settings);
			trigger(settings);
		});
		$('#editMode1, #editMode2').change(function () {
			settings.mode = $('#editMode1:checked, #editMode2:checked').val();
			trigger(settings);
		});
		trigger(settings);
	} else {
		// gallery
		for (item in opinions) {
			if (opinions.hasOwnProperty(item)) {
				chartTarget = '#chart-' + item.toString();
				// if settigns are embedded in the JSON then use them rather than defaults
				type = ['dos', 'spaeth', 'genealogy'][item % 3];

				height = setHeight(chartTarget, false);

				used = drawGraph(chartTarget, opinions[item], type, 'cat', height, 3, 'view', item);
				dissent = degreeOfDissent(used);
				attachDoDInfo('#dod-info-' + item.toString(), dissent);
			}
		}
	}
});
