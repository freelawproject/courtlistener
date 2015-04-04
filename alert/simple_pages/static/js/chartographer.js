/*!
 Chartographer 0.1.0 (https://github.com/danmane/chartogrpaher)
 Copyright 2014 Palantir Technologies
 Licensed under MIT (https://github.com/danmane/chartographer/blob/master/LICENSE)

 ************************************************
 **          Looking for readable source?      **
 **    Check out the .ts (typescript) file!    **
 ************************************************

 */

var __extends = this.__extends || function (d, b) {
    for (var p in b) if (b.hasOwnProperty(p)) d[p] = b[p];
    function __() { this.constructor = d; }
    __.prototype = b.prototype;
    d.prototype = new __();
};
var Chartographer;
(function (Chartographer) {
    var Chart = (function () {
        function Chart(datasets, spec) {
            this._xAccessor = "x";
            this._yAccessor = "y";
            this.colorVar = "fill";
            this.isNewStylePlot = false;
            this.hasDeployed = false;
            if (datasets instanceof Array)
                datasets = { "": datasets };
            datasets = d3.entries(datasets);
            this.datasets = datasets.map(function (kv) { return makeDataset(kv.key, kv.value); });
        }
        Chart.prototype.xType = function (t) {
            this._xType = this.setType(t, true);
            return this;
        };
        Chart.prototype.yType = function (t) {
            this._yType = this.setType(t, false);
            return this;
        };
        Chart.prototype.xAccessor = function (accessor) {
            this._xAccessor = accessor;
            return this;
        };
        Chart.prototype.yAccessor = function (accessor) {
            this._yAccessor = accessor;
            return this;
        };
        Chart.prototype.colors = function (colors) {
            this.colorRange = colors;
            return this;
        };
        Chart.prototype.titleLabel = function (label) {
            this._titleLabel = label;
            return this;
        };
        Chart.prototype.xLabel = function (label) {
            this._xLabel = label;
            return this;
        };
        Chart.prototype.yLabel = function (label) {
            this._yLabel = label;
            return this;
        };
        Chart.prototype.renderTo = function (svg) {
            this.getComponents().table.renderTo(svg);
        };
        Chart.prototype._project = function (attr, accessor, scale) {
            if (this.isNewStylePlot) {
                this.plot.project(attr, accessor, scale);
            }
            else {
                this.plots.forEach(function (p) { return p.project(attr, accessor, scale); });
            }
        };
        Chart.prototype._generatePlots = function (x, y) {
            var _this = this;
            if (this.isNewStylePlot) {
                this.plot = new Plottable.Plot[this.plotType](x, y);
                this.datasets.forEach(function (d) { return _this.plot.addDataset(d.metadata()[nameKey], d); });
            }
            else {
                this.plots = this.datasets.map(function (d) { return new Plottable.Plot[_this.plotType](x, y).addDataset(d); });
            }
        };
        Chart.prototype.setType = function (t, isX) {
            t = t.toLowerCase();
            if (t === "time" && !isX)
                throw new Error("Can't use time as y-type");
            if (validTypes.indexOf(t) === -1)
                throw new Error("Unrecognized type" + t);
            if (t === "log")
                t = "modifiedLog";
            return t;
        };
        Chart.prototype.deduceType = function (accessor, dataset) {
            var data = dataset.data();
            var a = typeof (accessor) === "string" ? function (x) { return x[accessor]; } : accessor;
            var d = a(data[0]);
            if (d instanceof Date)
                return "time";
            if (typeof (d) === "number")
                return "linear";
            if (typeof (d) === "string")
                return "ordinal";
            console.log("Data type couldn't be deduced; here's an example");
            console.log(d);
            throw new Error("Unrecognized data type");
        };
        Chart.prototype.modifyDataForNewStylePlot = function () {
            this.datasets.forEach(function (dataset) {
                var key = dataset.metadata()[nameKey];
                dataset.data().forEach(function (v) { return v[nameKey] = key; });
            });
        };
        Chart.prototype.getComponents = function () {
            if (this.isNewStylePlot)
                this.modifyDataForNewStylePlot();
            this._xType || (this._xType = this.deduceType(this._xAccessor, this.datasets[0]));
            this._yType || (this._yType = this.deduceType(this._yAccessor, this.datasets[0]));
            var xScale = new Plottable.Scale[camelCase(this._xType)]();
            var yScale = new Plottable.Scale[camelCase(this._yType)]();
            var colorScale = new Plottable.Scale.Color();
            if (this.colorRange)
                colorScale.range(this.colorRange);
            var xScaleForGridlines = this._xType === "ordinal" ? null : xScale;
            var yScaleForGridlines = this._yType === "ordinal" ? null : yScale;
            var gridlines = new Plottable.Component.Gridlines(xScaleForGridlines, yScaleForGridlines);
            var legend = colorScale.domain().length > 1 ? new Plottable.Component.HorizontalLegend(colorScale) : null;
            this._generatePlots(xScale, yScale);
            this._project("x", this._xAccessor, xScale);
            this._project("y", this._yAccessor, yScale);
            var colorAccessor = this.isNewStylePlot ? nameKey : function (d, i, m) { return m[nameKey]; };
            this._project(this.colorVar, colorAccessor, colorScale);
            var center = this.plot || new Plottable.Component.Group(this.plots);
            center.merge(gridlines);
            var xAxis = new Plottable.Axis[type2axis[this._xType]](xScale, "bottom");
            var yAxis = new Plottable.Axis[type2axis[this._yType]](yScale, "left");
            var titleLabel = this._titleLabel ? new Plottable.Component.TitleLabel(this._titleLabel) : null;
            var xLabel = this._xLabel ? new Plottable.Component.AxisLabel(this._xLabel) : null;
            var yLabel = this._yLabel ? new Plottable.Component.AxisLabel(this._yLabel, "left") : null;
            var table = new Plottable.Component.Table([
                [null, null, titleLabel],
                [null, null, legend],
                [yLabel, yAxis, center],
                [null, null, xAxis],
                [null, null, xLabel]
            ]);
            table.classed("chartographer", true);
            var chartComponents = {
                xScale: xScale,
                yScale: yScale,
                colorScale: colorScale,
                gridlines: gridlines,
                legend: legend,
                xAxis: xAxis,
                yAxis: yAxis,
                center: center,
                plot: this.plot,
                plots: this.plots,
                titleLabel: titleLabel,
                xLabel: xLabel,
                yLabel: yLabel,
                table: table
            };
            return chartComponents;
        };
        return Chart;
    })();
    Chartographer.Chart = Chart;
    var LineChart = (function (_super) {
        __extends(LineChart, _super);
        function LineChart() {
            _super.apply(this, arguments);
            this.plotType = "Line";
            this.colorVar = "stroke";
        }
        return LineChart;
    })(Chart);
    Chartographer.LineChart = LineChart;
    var ScatterChart = (function (_super) {
        __extends(ScatterChart, _super);
        function ScatterChart() {
            _super.apply(this, arguments);
            this.plotType = "Scatter";
        }
        return ScatterChart;
    })(Chart);
    Chartographer.ScatterChart = ScatterChart;
    var BarChart = (function (_super) {
        __extends(BarChart, _super);
        function BarChart() {
            _super.apply(this, arguments);
            this.plotType = "ClusteredBar";
            this.isNewStylePlot = true;
        }
        return BarChart;
    })(Chart);
    Chartographer.BarChart = BarChart;
    var StackedBarChart = (function (_super) {
        __extends(StackedBarChart, _super);
        function StackedBarChart() {
            _super.apply(this, arguments);
            this.plotType = "StackedBar";
            this.isNewStylePlot = true;
        }
        return StackedBarChart;
    })(BarChart);
    Chartographer.StackedBarChart = StackedBarChart;
    var nameKey = "_chartographer_name";
    var makeDataset = function (key, data) { return new Plottable.Dataset(data, { "_chartographer_name": key }); };
    var validTypes = ["linear", "log", "ordinal", "time"];
    var camelCase = function (s) { return s[0].toUpperCase() + s.substring(1); };
    var type2axis = { linear: "Numeric", modifiedLog: "Numeric", ordinal: "Category", time: "Time" };
})(Chartographer || (Chartographer = {}));
