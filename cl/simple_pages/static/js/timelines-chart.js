// Version 2.12.1 timelines-chart - https://github.com/vasturiano/timelines-chart
!function(t, n) {
	"object" == typeof exports && "undefined" != typeof module ? module.exports = n() : "function" == typeof define && define.amd ? define(n) : (t = "undefined" != typeof globalThis ? globalThis : t || self).TimelinesChart = n()
}(this, (function() {
	"use strict";
	function t(t) {
		return function(t) {
				if (Array.isArray(t))
					return n(t)
			}(t) || function(t) {
				if ("undefined" != typeof Symbol && null != t[Symbol.iterator] || null != t["@@iterator"])
					return Array.from(t)
			}(t) || function(t, e) {
				if (!t)
					return;
				if ("string" == typeof t)
					return n(t, e);
				var r = Object.prototype.toString.call(t).slice(8, -1);
				"Object" === r && t.constructor && (r = t.constructor.name);
				if ("Map" === r || "Set" === r)
					return Array.from(t);
				if ("Arguments" === r || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(r))
					return n(t, e)
			}(t) || function() {
				throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")
			}()
	}
	function n(t, n) {
		(null == n || n > t.length) && (n = t.length);
		for (var e = 0, r = new Array(n); e < n; e++)
			r[e] = t[e];
		return r
	}
	function e(t, n, e) {
		var r,
			i,
			a,
			o,
			u;
		function l() {
			var s = Date.now() - o;
			s < n && s >= 0 ? r = setTimeout(l, n - s) : (r = null, e || (u = t.apply(a, i), a = i = null))
		}
		null == n && (n = 100);
		var s = function() {
			a = this,
			i = arguments,
			o = Date.now();
			var s = e && !r;
			return r || (r = setTimeout(l, n)), s && (u = t.apply(a, i), a = i = null), u
		};
		return s.clear = function() {
			r && (clearTimeout(r), r = null)
		}, s.flush = function() {
			r && (u = t.apply(a, i), a = i = null, clearTimeout(r), r = null)
		}, s
	}
	!function(t, n) {
		void 0 === n && (n = {});
		var e = n.insertAt;
		if (t && "undefined" != typeof document) {
			var r = document.head || document.getElementsByTagName("head")[0],
				i = document.createElement("style");
			i.type = "text/css",
			"top" === e && r.firstChild ? r.insertBefore(i, r.firstChild) : r.appendChild(i),
			i.styleSheet ? i.styleSheet.cssText = t : i.appendChild(document.createTextNode(t))
		}
	}('.timelines-chart {\n\n  text-align: center;\n\n  /* Cancel selection interaction */\n  -webkit-touch-callout: none;\n  -webkit-user-select: none;\n  -khtml-user-select: none;\n  -moz-user-select: none;\n  -ms-user-select: none;\n  user-select: none;\n}\n\n  .timelines-chart .axises line, .timelines-chart .axises path {\n      stroke: #808080;\n    }\n\n  .timelines-chart .axises .x-axis {\n      font: 12px sans-serif;\n    }\n\n  .timelines-chart .axises .x-grid line {\n      stroke: #D3D3D3;\n    }\n\n  .timelines-chart .axises .y-axis line, .timelines-chart .axises .y-axis path, .timelines-chart .axises .grp-axis line, .timelines-chart .axises .grp-axis path {\n        stroke: none;\n      }\n\n  .timelines-chart .axises .y-axis text, .timelines-chart .axises .grp-axis text {\n        fill: #2F4F4F;\n      }\n\n  .timelines-chart line.x-axis-date-marker {\n    stroke-width: 1;\n    stroke: #293cb7;\n    fill: "none";\n  }\n\n  .timelines-chart .series-group {\n    fill-opacity: 0.6;\n    stroke: #808080;\n    stroke-opacity: 0.2;\n  }\n\n  .timelines-chart .series-segment {\n    stroke: none;\n  }\n\n  .timelines-chart .series-group, .timelines-chart .series-segment {\n    cursor: crosshair;\n  }\n\n  .timelines-chart .legend {\n    font-family: Sans-Serif;\n  }\n\n  .timelines-chart .legend .legendText {\n      fill: #666;\n    }\n\n  .timelines-chart .reset-zoom-btn {\n    font-family: sans-serif;\n    fill: blue;\n    opacity: .6;\n    cursor: pointer;\n  }\n\n.brusher .grid-background {\n    fill: lightgrey;\n  }\n\n.brusher .axis path {\n    display: none;\n  }\n\n.brusher .tick text {\n    text-anchor: middle;\n  }\n\n.brusher .grid line, .brusher .grid path {\n      stroke: #fff;\n    }\n\n.chart-zoom-selection, .brusher .brush .selection {\n  stroke: blue;\n  stroke-opacity: 0.6;\n  fill: blue;\n  fill-opacity: 0.3;\n  shape-rendering: crispEdges;\n}\n\n.chart-tooltip {\n  color: #eee;\n  background: rgba(0,0,140,0.85);\n  padding: 5px;\n  border-radius: 3px;\n  font: 11px sans-serif;\n  z-index: 4000;\n}\n\n.chart-tooltip.group-tooltip {\n    font-size: 14px;\n  }\n\n.chart-tooltip.line-tooltip {\n    font-size: 13px;\n  }\n\n.chart-tooltip.group-tooltip, .chart-tooltip.line-tooltip {\n    font-weight: bold;\n  }\n\n.chart-tooltip.segment-tooltip {\n     text-align: center;\n  }'),
	e.debounce = e;
	var r = e;
	function i(t, n) {
		for (var e = 0; e < n.length; e++) {
			var r = n[e];
			r.enumerable = r.enumerable || !1,
			r.configurable = !0,
			"value" in r && (r.writable = !0),
			Object.defineProperty(t, (i = r.key, a = void 0, "symbol" == typeof (a = function(t, n) {
				if ("object" != typeof t || null === t)
					return t;
				var e = t[Symbol.toPrimitive];
				if (void 0 !== e) {
					var r = e.call(t, n || "default");
					if ("object" != typeof r)
						return r;
					throw new TypeError("@@toPrimitive must return a primitive value.")
				}
				return ("string" === n ? String : Number)(t)
			}(i, "string")) ? a : String(a)), r)
		}
		var i,
			a
	}
	function a(t, n, e) {
		return n && i(t.prototype, n), e && i(t, e), Object.defineProperty(t, "prototype", {
			writable: !1
		}), t
	}
	function o(t, n) {
		return function(t) {
				if (Array.isArray(t))
					return t
			}(t) || function(t, n) {
				var e = null == t ? null : "undefined" != typeof Symbol && t[Symbol.iterator] || t["@@iterator"];
				if (null != e) {
					var r,
						i,
						a,
						o,
						u = [],
						l = !0,
						s = !1;
					try {
						if (a = (e = e.call(t)).next, 0 === n) {
							if (Object(e) !== e)
								return;
							l = !1
						} else
							for (; !(l = (r = a.call(e)).done) && (u.push(r.value), u.length !== n); l = !0)
								;
					} catch (t) {
						s = !0,
						i = t
					} finally {
						try {
							if (!l && null != e.return && (o = e.return(), Object(o) !== o))
								return
						} finally {
							if (s)
								throw i
						}
					}
					return u
				}
			}(t, n) || function(t, n) {
				if (!t)
					return;
				if ("string" == typeof t)
					return u(t, n);
				var e = Object.prototype.toString.call(t).slice(8, -1);
				"Object" === e && t.constructor && (e = t.constructor.name);
				if ("Map" === e || "Set" === e)
					return Array.from(t);
				if ("Arguments" === e || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(e))
					return u(t, n)
			}(t, n) || function() {
				throw new TypeError("Invalid attempt to destructure non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")
			}()
	}
	function u(t, n) {
		(null == n || n > t.length) && (n = t.length);
		for (var e = 0, r = new Array(n); e < n; e++)
			r[e] = t[e];
		return r
	}
	var l = a((function t(n, e) {
		var r = e.default,
			i = void 0 === r ? null : r,
			a = e.triggerUpdate,
			o = void 0 === a || a,
			u = e.onChange,
			l = void 0 === u ? function(t, n) {} : u;
		!function(t, n) {
			if (!(t instanceof n))
				throw new TypeError("Cannot call a class as a function")
		}(this, t),
		this.name = n,
		this.defaultVal = i,
		this.triggerUpdate = o,
		this.onChange = l
	}));
	function s(t) {
		var n = t.stateInit,
			e = void 0 === n ? function() {
				return {}
			} : n,
			i = t.props,
			a = void 0 === i ? {} : i,
			u = t.methods,
			s = void 0 === u ? {} : u,
			c = t.aliases,
			f = void 0 === c ? {} : c,
			h = t.init,
			p = void 0 === h ? function() {} : h,
			g = t.update,
			d = void 0 === g ? function() {} : g,
			m = Object.keys(a).map((function(t) {
				return new l(t, a[t])
			}));
		return function() {
			var t = arguments.length > 0 && void 0 !== arguments[0] ? arguments[0] : {},
				n = Object.assign({}, e instanceof Function ? e(t) : e, {
					initialised: !1
				}),
				i = {};
			function a(n) {
				return u(n, t), l(), a
			}
			var u = function(t, e) {
					p.call(a, t, n, e),
					n.initialised = !0
				},
				l = r((function() {
					n.initialised && (d.call(a, n, i), i = {})
				}), 1);
			return m.forEach((function(t) {
				a[t.name] = function(t) {
					var e = t.name,
						r = t.triggerUpdate,
						o = void 0 !== r && r,
						u = t.onChange,
						s = void 0 === u ? function(t, n) {} : u,
						c = t.defaultVal,
						f = void 0 === c ? null : c;
					return function(t) {
						var r = n[e];
						if (!arguments.length)
							return r;
						var u = void 0 === t ? f : t;
						return n[e] = u, s.call(a, u, n, r), !i.hasOwnProperty(e) && (i[e] = r), o && l(), a
					}
				}(t)
			})), Object.keys(s).forEach((function(t) {
				a[t] = function() {
					for (var e, r = arguments.length, i = new Array(r), o = 0; o < r; o++)
						i[o] = arguments[o];
					return (e = s[t]).call.apply(e, [a, n].concat(i))
				}
			})), Object.entries(f).forEach((function(t) {
				var n = o(t, 2),
					e = n[0],
					r = n[1];
				return a[e] = a[r]
			})), a.resetProps = function() {
				return m.forEach((function(t) {
					a[t.name](t.defaultVal)
				})), a
			}, a.resetProps(), n._rerender = l, a
		}
	}
	function c(t, n) {
		return null == t || null == n ? NaN : t < n ? -1 : t > n ? 1 : t >= n ? 0 : NaN
	}
	function f(t, n) {
		return null == t || null == n ? NaN : n < t ? -1 : n > t ? 1 : n >= t ? 0 : NaN
	}
	function h(t) {
		let n,
			e,
			r;
		function i(t, r, i=0, a=t.length) {
			if (i < a) {
				if (0 !== n(r, r))
					return a;
				do {
					const n = i + a >>> 1;
					e(t[n], r) < 0 ? i = n + 1 : a = n
				} while (i < a)
			}
			return i
		}
		return 2 !== t.length ? (n = c, e = (n, e) => c(t(n), e), r = (n, e) => t(n) - e) : (n = t === c || t === f ? t : p, e = t, r = t), {
			left: i,
			center: function(t, n, e=0, a=t.length) {
				const o = i(t, n, e, a - 1);
				return o > e && r(t[o - 1], n) > -r(t[o], n) ? o - 1 : o
			},
			right: function(t, r, i=0, a=t.length) {
				if (i < a) {
					if (0 !== n(r, r))
						return a;
					do {
						const n = i + a >>> 1;
						e(t[n], r) <= 0 ? i = n + 1 : a = n
					} while (i < a)
				}
				return i
			}
		}
	}
	function p() {
		return 0
	}
	const g = h(c).right;
	h((function(t) {
		return null === t ? NaN : +t
	})).center;
	var d = g;
	class m extends Map {
		constructor(t, n=y)
		{
			if (super(), Object.defineProperties(this, {
				_intern: {
					value: new Map
				},
				_key: {
					value: n
				}
			}), null != t)
				for (const [n, e] of t)
					this.set(n, e)
		}
		get(t)
		{
			return super.get(v(this, t))
		}
		has(t)
		{
			return super.has(v(this, t))
		}
		set(t, n)
		{
			return super.set(function({_intern: t, _key: n}, e) {
				const r = n(e);
				return t.has(r) ? t.get(r) : (t.set(r, e), e)
			}(this, t), n)
		}
		delete(t)
		{
			return super.delete(function({_intern: t, _key: n}, e) {
				const r = n(e);
				t.has(r) && (e = t.get(r), t.delete(r));
				return e
			}(this, t))
		}
	}
	function v({_intern: t, _key: n}, e) {
		const r = n(e);
		return t.has(r) ? t.get(r) : e
	}
	function y(t) {
		return null !== t && "object" == typeof t ? t.valueOf() : t
	}
	const b = Math.sqrt(50),
		w = Math.sqrt(10),
		_ = Math.sqrt(2);
	function x(t, n, e) {
		const r = (n - t) / Math.max(0, e),
			i = Math.floor(Math.log10(r)),
			a = r / Math.pow(10, i),
			o = a >= b ? 10 : a >= w ? 5 : a >= _ ? 2 : 1;
		let u,
			l,
			s;
		return i < 0 ? (s = Math.pow(10, -i) / o, u = Math.round(t * s), l = Math.round(n * s), u / s < t && ++u, l / s > n && --l, s = -s) : (s = Math.pow(10, i) * o, u = Math.round(t / s), l = Math.round(n / s), u * s < t && ++u, l * s > n && --l), l < u && .5 <= e && e < 2 ? x(t, n, 2 * e) : [u, l, s]
	}
	function M(t, n, e) {
		return x(t = +t, n = +n, e = +e)[2]
	}
	function A(t, n, e) {
		e = +e;
		const r = (n = +n) < (t = +t),
			i = r ? M(n, t, e) : M(t, n, e);
		return (r ? -1 : 1) * (i < 0 ? 1 / -i : i)
	}
	function S(t, n) {
		let e;
		if (void 0 === n)
			for (const n of t)
				null != n && (e < n || void 0 === e && n >= n) && (e = n);
		else {
			let r = -1;
			for (let i of t)
				null != (i = n(i, ++r, t)) && (e < i || void 0 === e && i >= i) && (e = i)
		}
		return e
	}
	function k(t, n) {
		let e;
		if (void 0 === n)
			for (const n of t)
				null != n && (e > n || void 0 === e && n >= n) && (e = n);
		else {
			let r = -1;
			for (let i of t)
				null != (i = n(i, ++r, t)) && (e > i || void 0 === e && i >= i) && (e = i)
		}
		return e
	}
	function C(t, n, e) {
		t = +t,
		n = +n,
		e = (i = arguments.length) < 2 ? (n = t, t = 0, 1) : i < 3 ? 1 : +e;
		for (var r = -1, i = 0 | Math.max(0, Math.ceil((n - t) / e)), a = new Array(i); ++r < i;)
			a[r] = t + r * e;
		return a
	}
	function T(t) {
		return t
	}
	var D = 1,
		N = 2,
		z = 3,
		E = 4,
		F = 1e-6;
	function H(t) {
		return "translate(" + t + ",0)"
	}
	function L(t) {
		return "translate(0," + t + ")"
	}
	function U(t) {
		return n => +t(n)
	}
	function R(t, n) {
		return n = Math.max(0, t.bandwidth() - 2 * n) / 2, t.round() && (n = Math.round(n)), e => +t(e) + n
	}
	function Y() {
		return !this.__axis
	}
	function O(t, n) {
		var e = [],
			r = null,
			i = null,
			a = 6,
			o = 6,
			u = 3,
			l = "undefined" != typeof window && window.devicePixelRatio > 1 ? 0 : .5,
			s = t === D || t === E ? -1 : 1,
			c = t === E || t === N ? "x" : "y",
			f = t === D || t === z ? H : L;
		function h(h) {
			var p = null == r ? n.ticks ? n.ticks.apply(n, e) : n.domain() : r,
				g = null == i ? n.tickFormat ? n.tickFormat.apply(n, e) : T : i,
				d = Math.max(a, 0) + u,
				m = n.range(),
				v = +m[0] + l,
				y = +m[m.length - 1] + l,
				b = (n.bandwidth ? R : U)(n.copy(), l),
				w = h.selection ? h.selection() : h,
				_ = w.selectAll(".domain").data([null]),
				x = w.selectAll(".tick").data(p, n).order(),
				M = x.exit(),
				A = x.enter().append("g").attr("class", "tick"),
				S = x.select("line"),
				k = x.select("text");
			_ = _.merge(_.enter().insert("path", ".tick").attr("class", "domain").attr("stroke", "currentColor")),
			x = x.merge(A),
			S = S.merge(A.append("line").attr("stroke", "currentColor").attr(c + "2", s * a)),
			k = k.merge(A.append("text").attr("fill", "currentColor").attr(c, s * d).attr("dy", t === D ? "0em" : t === z ? "0.71em" : "0.32em")),
			h !== w && (_ = _.transition(h), x = x.transition(h), S = S.transition(h), k = k.transition(h), M = M.transition(h).attr("opacity", F).attr("transform", (function(t) {
				return isFinite(t = b(t)) ? f(t + l) : this.getAttribute("transform")
			})), A.attr("opacity", F).attr("transform", (function(t) {
				var n = this.parentNode.__axis;
				return f((n && isFinite(n = n(t)) ? n : b(t)) + l)
			}))),
			M.remove(),
			_.attr("d", t === E || t === N ? o ? "M" + s * o + "," + v + "H" + l + "V" + y + "H" + s * o : "M" + l + "," + v + "V" + y : o ? "M" + v + "," + s * o + "V" + l + "H" + y + "V" + s * o : "M" + v + "," + l + "H" + y),
			x.attr("opacity", 1).attr("transform", (function(t) {
				return f(b(t) + l)
			})),
			S.attr(c + "2", s * a),
			k.attr(c, s * d).text(g),
			w.filter(Y).attr("fill", "none").attr("font-size", 10).attr("font-family", "sans-serif").attr("text-anchor", t === N ? "start" : t === E ? "end" : "middle"),
			w.each((function() {
				this.__axis = b
			}))
		}
		return h.scale = function(t) {
			return arguments.length ? (n = t, h) : n
		}, h.ticks = function() {
			return e = Array.from(arguments), h
		}, h.tickArguments = function(t) {
			return arguments.length ? (e = null == t ? [] : Array.from(t), h) : e.slice()
		}, h.tickValues = function(t) {
			return arguments.length ? (r = null == t ? null : Array.from(t), h) : r && r.slice()
		}, h.tickFormat = function(t) {
			return arguments.length ? (i = t, h) : i
		}, h.tickSize = function(t) {
			return arguments.length ? (a = o = +t, h) : a
		}, h.tickSizeInner = function(t) {
			return arguments.length ? (a = +t, h) : a
		}, h.tickSizeOuter = function(t) {
			return arguments.length ? (o = +t, h) : o
		}, h.tickPadding = function(t) {
			return arguments.length ? (u = +t, h) : u
		}, h.offset = function(t) {
			return arguments.length ? (l = +t, h) : l
		}, h
	}
	function P(t) {
		return O(z, t)
	}
	function j(t, n) {
		switch (arguments.length) {
		case 0:
			break;
		case 1:
			this.range(t);
			break;
		default:
			this.range(n).domain(t)
		}
		return this
	}
	function $(t, n) {
		switch (arguments.length) {
		case 0:
			break;
		case 1:
			"function" == typeof t ? this.interpolator(t) : this.range(t);
			break;
		default:
			this.domain(t),
			"function" == typeof n ? this.interpolator(n) : this.range(n)
		}
		return this
	}
	const I = Symbol("implicit");
	function q() {
		var t = new m,
			n = [],
			e = [],
			r = I;
		function i(i) {
			let a = t.get(i);
			if (void 0 === a) {
				if (r !== I)
					return r;
				t.set(i, a = n.push(i) - 1)
			}
			return e[a % e.length]
		}
		return i.domain = function(e) {
			if (!arguments.length)
				return n.slice();
			n = [],
			t = new m;
			for (const r of e)
				t.has(r) || t.set(r, n.push(r) - 1);
			return i
		}, i.range = function(t) {
			return arguments.length ? (e = Array.from(t), i) : e.slice()
		}, i.unknown = function(t) {
			return arguments.length ? (r = t, i) : r
		}, i.copy = function() {
			return q(n, e).unknown(r)
		}, j.apply(i, arguments), i
	}
	function B() {
		var t,
			n,
			e = q().unknown(void 0),
			r = e.domain,
			i = e.range,
			a = 0,
			o = 1,
			u = !1,
			l = 0,
			s = 0,
			c = .5;
		function f() {
			var e = r().length,
				f = o < a,
				h = f ? o : a,
				p = f ? a : o;
			t = (p - h) / Math.max(1, e - l + 2 * s),
			u && (t = Math.floor(t)),
			h += (p - h - t * (e - l)) * c,
			n = t * (1 - l),
			u && (h = Math.round(h), n = Math.round(n));
			var g = C(e).map((function(n) {
				return h + t * n
			}));
			return i(f ? g.reverse() : g)
		}
		return delete e.unknown, e.domain = function(t) {
			return arguments.length ? (r(t), f()) : r()
		}, e.range = function(t) {
			return arguments.length ? ([a, o] = t, a = +a, o = +o, f()) : [a, o]
		}, e.rangeRound = function(t) {
			return [a, o] = t, a = +a, o = +o, u = !0, f()
		}, e.bandwidth = function() {
			return n
		}, e.step = function() {
			return t
		}, e.round = function(t) {
			return arguments.length ? (u = !!t, f()) : u
		}, e.padding = function(t) {
			return arguments.length ? (l = Math.min(1, s = +t), f()) : l
		}, e.paddingInner = function(t) {
			return arguments.length ? (l = Math.min(1, t), f()) : l
		}, e.paddingOuter = function(t) {
			return arguments.length ? (s = +t, f()) : s
		}, e.align = function(t) {
			return arguments.length ? (c = Math.max(0, Math.min(1, t)), f()) : c
		}, e.copy = function() {
			return B(r(), [a, o]).round(u).paddingInner(l).paddingOuter(s).align(c)
		}, j.apply(f(), arguments)
	}
	function X(t) {
		var n = t.copy;
		return t.padding = t.paddingOuter, delete t.paddingInner, delete t.paddingOuter, t.copy = function() {
			return X(n())
		}, t
	}
	function V() {
		return X(B.apply(null, arguments).paddingInner(1))
	}
	function W(t, n, e) {
		t.prototype = n.prototype = e,
		e.constructor = t
	}
	function G(t, n) {
		var e = Object.create(t.prototype);
		for (var r in n)
			e[r] = n[r];
		return e
	}
	function Z() {}
	var Q = .7,
		J = 1 / Q,
		K = "\\s*([+-]?\\d+)\\s*",
		tt = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)\\s*",
		nt = "\\s*([+-]?(?:\\d*\\.)?\\d+(?:[eE][+-]?\\d+)?)%\\s*",
		et = /^#([0-9a-f]{3,8})$/,
		rt = new RegExp(`^rgb\\(${K},${K},${K}\\)$`),
		it = new RegExp(`^rgb\\(${nt},${nt},${nt}\\)$`),
		at = new RegExp(`^rgba\\(${K},${K},${K},${tt}\\)$`),
		ot = new RegExp(`^rgba\\(${nt},${nt},${nt},${tt}\\)$`),
		ut = new RegExp(`^hsl\\(${tt},${nt},${nt}\\)$`),
		lt = new RegExp(`^hsla\\(${tt},${nt},${nt},${tt}\\)$`),
		st = {
			aliceblue: 15792383,
			antiquewhite: 16444375,
			aqua: 65535,
			aquamarine: 8388564,
			azure: 15794175,
			beige: 16119260,
			bisque: 16770244,
			black: 0,
			blanchedalmond: 16772045,
			blue: 255,
			blueviolet: 9055202,
			brown: 10824234,
			burlywood: 14596231,
			cadetblue: 6266528,
			chartreuse: 8388352,
			chocolate: 13789470,
			coral: 16744272,
			cornflowerblue: 6591981,
			cornsilk: 16775388,
			crimson: 14423100,
			cyan: 65535,
			darkblue: 139,
			darkcyan: 35723,
			darkgoldenrod: 12092939,
			darkgray: 11119017,
			darkgreen: 25600,
			darkgrey: 11119017,
			darkkhaki: 12433259,
			darkmagenta: 9109643,
			darkolivegreen: 5597999,
			darkorange: 16747520,
			darkorchid: 10040012,
			darkred: 9109504,
			darksalmon: 15308410,
			darkseagreen: 9419919,
			darkslateblue: 4734347,
			darkslategray: 3100495,
			darkslategrey: 3100495,
			darkturquoise: 52945,
			darkviolet: 9699539,
			deeppink: 16716947,
			deepskyblue: 49151,
			dimgray: 6908265,
			dimgrey: 6908265,
			dodgerblue: 2003199,
			firebrick: 11674146,
			floralwhite: 16775920,
			forestgreen: 2263842,
			fuchsia: 16711935,
			gainsboro: 14474460,
			ghostwhite: 16316671,
			gold: 16766720,
			goldenrod: 14329120,
			gray: 8421504,
			green: 32768,
			greenyellow: 11403055,
			grey: 8421504,
			honeydew: 15794160,
			hotpink: 16738740,
			indianred: 13458524,
			indigo: 4915330,
			ivory: 16777200,
			khaki: 15787660,
			lavender: 15132410,
			lavenderblush: 16773365,
			lawngreen: 8190976,
			lemonchiffon: 16775885,
			lightblue: 11393254,
			lightcoral: 15761536,
			lightcyan: 14745599,
			lightgoldenrodyellow: 16448210,
			lightgray: 13882323,
			lightgreen: 9498256,
			lightgrey: 13882323,
			lightpink: 16758465,
			lightsalmon: 16752762,
			lightseagreen: 2142890,
			lightskyblue: 8900346,
			lightslategray: 7833753,
			lightslategrey: 7833753,
			lightsteelblue: 11584734,
			lightyellow: 16777184,
			lime: 65280,
			limegreen: 3329330,
			linen: 16445670,
			magenta: 16711935,
			maroon: 8388608,
			mediumaquamarine: 6737322,
			mediumblue: 205,
			mediumorchid: 12211667,
			mediumpurple: 9662683,
			mediumseagreen: 3978097,
			mediumslateblue: 8087790,
			mediumspringgreen: 64154,
			mediumturquoise: 4772300,
			mediumvioletred: 13047173,
			midnightblue: 1644912,
			mintcream: 16121850,
			mistyrose: 16770273,
			moccasin: 16770229,
			navajowhite: 16768685,
			navy: 128,
			oldlace: 16643558,
			olive: 8421376,
			olivedrab: 7048739,
			orange: 16753920,
			orangered: 16729344,
			orchid: 14315734,
			palegoldenrod: 15657130,
			palegreen: 10025880,
			paleturquoise: 11529966,
			palevioletred: 14381203,
			papayawhip: 16773077,
			peachpuff: 16767673,
			peru: 13468991,
			pink: 16761035,
			plum: 14524637,
			powderblue: 11591910,
			purple: 8388736,
			rebeccapurple: 6697881,
			red: 16711680,
			rosybrown: 12357519,
			royalblue: 4286945,
			saddlebrown: 9127187,
			salmon: 16416882,
			sandybrown: 16032864,
			seagreen: 3050327,
			seashell: 16774638,
			sienna: 10506797,
			silver: 12632256,
			skyblue: 8900331,
			slateblue: 6970061,
			slategray: 7372944,
			slategrey: 7372944,
			snow: 16775930,
			springgreen: 65407,
			steelblue: 4620980,
			tan: 13808780,
			teal: 32896,
			thistle: 14204888,
			tomato: 16737095,
			turquoise: 4251856,
			violet: 15631086,
			wheat: 16113331,
			white: 16777215,
			whitesmoke: 16119285,
			yellow: 16776960,
			yellowgreen: 10145074
		};
	function ct() {
		return this.rgb().formatHex()
	}
	function ft() {
		return this.rgb().formatRgb()
	}
	function ht(t) {
		var n,
			e;
		return t = (t + "").trim().toLowerCase(), (n = et.exec(t)) ? (e = n[1].length, n = parseInt(n[1], 16), 6 === e ? pt(n) : 3 === e ? new mt(n >> 8 & 15 | n >> 4 & 240, n >> 4 & 15 | 240 & n, (15 & n) << 4 | 15 & n, 1) : 8 === e ? gt(n >> 24 & 255, n >> 16 & 255, n >> 8 & 255, (255 & n) / 255) : 4 === e ? gt(n >> 12 & 15 | n >> 8 & 240, n >> 8 & 15 | n >> 4 & 240, n >> 4 & 15 | 240 & n, ((15 & n) << 4 | 15 & n) / 255) : null) : (n = rt.exec(t)) ? new mt(n[1], n[2], n[3], 1) : (n = it.exec(t)) ? new mt(255 * n[1] / 100, 255 * n[2] / 100, 255 * n[3] / 100, 1) : (n = at.exec(t)) ? gt(n[1], n[2], n[3], n[4]) : (n = ot.exec(t)) ? gt(255 * n[1] / 100, 255 * n[2] / 100, 255 * n[3] / 100, n[4]) : (n = ut.exec(t)) ? xt(n[1], n[2] / 100, n[3] / 100, 1) : (n = lt.exec(t)) ? xt(n[1], n[2] / 100, n[3] / 100, n[4]) : st.hasOwnProperty(t) ? pt(st[t]) : "transparent" === t ? new mt(NaN, NaN, NaN, 0) : null
	}
	function pt(t) {
		return new mt(t >> 16 & 255, t >> 8 & 255, 255 & t, 1)
	}
	function gt(t, n, e, r) {
		return r <= 0 && (t = n = e = NaN), new mt(t, n, e, r)
	}
	function dt(t, n, e, r) {
		return 1 === arguments.length ? ((i = t) instanceof Z || (i = ht(i)), i ? new mt((i = i.rgb()).r, i.g, i.b, i.opacity) : new mt) : new mt(t, n, e, null == r ? 1 : r);
		var i
	}
	function mt(t, n, e, r) {
		this.r = +t,
		this.g = +n,
		this.b = +e,
		this.opacity = +r
	}
	function vt() {
		return `#${_t(this.r)}${_t(this.g)}${_t(this.b)}`
	}
	function yt() {
		const t = bt(this.opacity);
		return `${1 === t ? "rgb(" : "rgba("}${wt(this.r)}, ${wt(this.g)}, ${wt(this.b)}${1 === t ? ")" : `, ${t})`}`
	}
	function bt(t) {
		return isNaN(t) ? 1 : Math.max(0, Math.min(1, t))
	}
	function wt(t) {
		return Math.max(0, Math.min(255, Math.round(t) || 0))
	}
	function _t(t) {
		return ((t = wt(t)) < 16 ? "0" : "") + t.toString(16)
	}
	function xt(t, n, e, r) {
		return r <= 0 ? t = n = e = NaN : e <= 0 || e >= 1 ? t = n = NaN : n <= 0 && (t = NaN), new At(t, n, e, r)
	}
	function Mt(t) {
		if (t instanceof At)
			return new At(t.h, t.s, t.l, t.opacity);
		if (t instanceof Z || (t = ht(t)), !t)
			return new At;
		if (t instanceof At)
			return t;
		var n = (t = t.rgb()).r / 255,
			e = t.g / 255,
			r = t.b / 255,
			i = Math.min(n, e, r),
			a = Math.max(n, e, r),
			o = NaN,
			u = a - i,
			l = (a + i) / 2;
		return u ? (o = n === a ? (e - r) / u + 6 * (e < r) : e === a ? (r - n) / u + 2 : (n - e) / u + 4, u /= l < .5 ? a + i : 2 - a - i, o *= 60) : u = l > 0 && l < 1 ? 0 : o, new At(o, u, l, t.opacity)
	}
	function At(t, n, e, r) {
		this.h = +t,
		this.s = +n,
		this.l = +e,
		this.opacity = +r
	}
	function St(t) {
		return (t = (t || 0) % 360) < 0 ? t + 360 : t
	}
	function kt(t) {
		return Math.max(0, Math.min(1, t || 0))
	}
	function Ct(t, n, e) {
		return 255 * (t < 60 ? n + (e - n) * t / 60 : t < 180 ? e : t < 240 ? n + (e - n) * (240 - t) / 60 : n)
	}
	W(Z, ht, {
		copy(t) {
			return Object.assign(new this.constructor, this, t)
		},
		displayable() {
			return this.rgb().displayable()
		},
		hex: ct,
		formatHex: ct,
		formatHex8: function() {
			return this.rgb().formatHex8()
		},
		formatHsl: function() {
			return Mt(this).formatHsl()
		},
		formatRgb: ft,
		toString: ft
	}),
	W(mt, dt, G(Z, {
		brighter(t) {
			return t = null == t ? J : Math.pow(J, t), new mt(this.r * t, this.g * t, this.b * t, this.opacity)
		},
		darker(t) {
			return t = null == t ? Q : Math.pow(Q, t), new mt(this.r * t, this.g * t, this.b * t, this.opacity)
		},
		rgb() {
			return this
		},
		clamp() {
			return new mt(wt(this.r), wt(this.g), wt(this.b), bt(this.opacity))
		},
		displayable() {
			return -.5 <= this.r && this.r < 255.5 && -.5 <= this.g && this.g < 255.5 && -.5 <= this.b && this.b < 255.5 && 0 <= this.opacity && this.opacity <= 1
		},
		hex: vt,
		formatHex: vt,
		formatHex8: function() {
			return `#${_t(this.r)}${_t(this.g)}${_t(this.b)}${_t(255 * (isNaN(this.opacity) ? 1 : this.opacity))}`
		},
		formatRgb: yt,
		toString: yt
	})),
	W(At, (function(t, n, e, r) {
		return 1 === arguments.length ? Mt(t) : new At(t, n, e, null == r ? 1 : r)
	}), G(Z, {
		brighter(t) {
			return t = null == t ? J : Math.pow(J, t), new At(this.h, this.s, this.l * t, this.opacity)
		},
		darker(t) {
			return t = null == t ? Q : Math.pow(Q, t), new At(this.h, this.s, this.l * t, this.opacity)
		},
		rgb() {
			var t = this.h % 360 + 360 * (this.h < 0),
				n = isNaN(t) || isNaN(this.s) ? 0 : this.s,
				e = this.l,
				r = e + (e < .5 ? e : 1 - e) * n,
				i = 2 * e - r;
			return new mt(Ct(t >= 240 ? t - 240 : t + 120, i, r), Ct(t, i, r), Ct(t < 120 ? t + 240 : t - 120, i, r), this.opacity)
		},
		clamp() {
			return new At(St(this.h), kt(this.s), kt(this.l), bt(this.opacity))
		},
		displayable() {
			return (0 <= this.s && this.s <= 1 || isNaN(this.s)) && 0 <= this.l && this.l <= 1 && 0 <= this.opacity && this.opacity <= 1
		},
		formatHsl() {
			const t = bt(this.opacity);
			return `${1 === t ? "hsl(" : "hsla("}${St(this.h)}, ${100 * kt(this.s)}%, ${100 * kt(this.l)}%${1 === t ? ")" : `, ${t})`}`
		}
	}));
	var Tt = t => () => t;
	function Dt(t) {
		return 1 == (t = +t) ? Nt : function(n, e) {
			return e - n ? function(t, n, e) {
				return t = Math.pow(t, e), n = Math.pow(n, e) - t, e = 1 / e, function(r) {
					return Math.pow(t + r * n, e)
				}
			}(n, e, t) : Tt(isNaN(n) ? e : n)
		}
	}
	function Nt(t, n) {
		var e = n - t;
		return e ? function(t, n) {
			return function(e) {
				return t + e * n
			}
		}(t, e) : Tt(isNaN(t) ? n : t)
	}
	var zt = function t(n) {
		var e = Dt(n);
		function r(t, n) {
			var r = e((t = dt(t)).r, (n = dt(n)).r),
				i = e(t.g, n.g),
				a = e(t.b, n.b),
				o = Nt(t.opacity, n.opacity);
			return function(n) {
				return t.r = r(n), t.g = i(n), t.b = a(n), t.opacity = o(n), t + ""
			}
		}
		return r.gamma = t, r
	}(1);
	var Et,
		Ft = (Et = function(t) {
			var n = t.length - 1;
			return function(e) {
				var r = e <= 0 ? e = 0 : e >= 1 ? (e = 1, n - 1) : Math.floor(e * n),
					i = t[r],
					a = t[r + 1],
					o = r > 0 ? t[r - 1] : 2 * i - a,
					u = r < n - 1 ? t[r + 2] : 2 * a - i;
				return function(t, n, e, r, i) {
					var a = t * t,
						o = a * t;
					return ((1 - 3 * t + 3 * a - o) * n + (4 - 6 * a + 3 * o) * e + (1 + 3 * t + 3 * a - 3 * o) * r + o * i) / 6
				}((e - r / n) * n, o, i, a, u)
			}
		}, function(t) {
			var n,
				e,
				r = t.length,
				i = new Array(r),
				a = new Array(r),
				o = new Array(r);
			for (n = 0; n < r; ++n)
				e = dt(t[n]),
				i[n] = e.r || 0,
				a[n] = e.g || 0,
				o[n] = e.b || 0;
			return i = Et(i), a = Et(a), o = Et(o), e.opacity = 1, function(t) {
				return e.r = i(t), e.g = a(t), e.b = o(t), e + ""
			}
		});
	function Ht(t, n) {
		n || (n = []);
		var e,
			r = t ? Math.min(n.length, t.length) : 0,
			i = n.slice();
		return function(a) {
			for (e = 0; e < r; ++e)
				i[e] = t[e] * (1 - a) + n[e] * a;
			return i
		}
	}
	function Lt(t, n) {
		var e,
			r = n ? n.length : 0,
			i = t ? Math.min(r, t.length) : 0,
			a = new Array(i),
			o = new Array(r);
		for (e = 0; e < i; ++e)
			a[e] = $t(t[e], n[e]);
		for (; e < r; ++e)
			o[e] = n[e];
		return function(t) {
			for (e = 0; e < i; ++e)
				o[e] = a[e](t);
			return o
		}
	}
	function Ut(t, n) {
		var e = new Date;
		return t = +t, n = +n, function(r) {
			return e.setTime(t * (1 - r) + n * r), e
		}
	}
	function Rt(t, n) {
		return t = +t, n = +n, function(e) {
			return t * (1 - e) + n * e
		}
	}
	function Yt(t, n) {
		var e,
			r = {},
			i = {};
		for (e in null !== t && "object" == typeof t || (t = {}), null !== n && "object" == typeof n || (n = {}), n)
			e in t ? r[e] = $t(t[e], n[e]) : i[e] = n[e];
		return function(t) {
			for (e in r)
				i[e] = r[e](t);
			return i
		}
	}
	var Ot = /[-+]?(?:\d+\.?\d*|\.?\d+)(?:[eE][-+]?\d+)?/g,
		Pt = new RegExp(Ot.source, "g");
	function jt(t, n) {
		var e,
			r,
			i,
			a = Ot.lastIndex = Pt.lastIndex = 0,
			o = -1,
			u = [],
			l = [];
		for (t += "", n += ""; (e = Ot.exec(t)) && (r = Pt.exec(n));)
			(i = r.index) > a && (i = n.slice(a, i), u[o] ? u[o] += i : u[++o] = i),
			(e = e[0]) === (r = r[0]) ? u[o] ? u[o] += r : u[++o] = r : (u[++o] = null, l.push({
				i: o,
				x: Rt(e, r)
			})),
			a = Pt.lastIndex;
		return a < n.length && (i = n.slice(a), u[o] ? u[o] += i : u[++o] = i), u.length < 2 ? l[0] ? function(t) {
			return function(n) {
				return t(n) + ""
			}
		}(l[0].x) : function(t) {
			return function() {
				return t
			}
		}(n) : (n = l.length, function(t) {
			for (var e, r = 0; r < n; ++r)
				u[(e = l[r]).i] = e.x(t);
			return u.join("")
		})
	}
	function $t(t, n) {
		var e,
			r,
			i = typeof n;
		return null == n || "boolean" === i ? Tt(n) : ("number" === i ? Rt : "string" === i ? (e = ht(n)) ? (n = e, zt) : jt : n instanceof ht ? zt : n instanceof Date ? Ut : (r = n, !ArrayBuffer.isView(r) || r instanceof DataView ? Array.isArray(n) ? Lt : "function" != typeof n.valueOf && "function" != typeof n.toString || isNaN(n) ? Yt : Rt : Ht))(t, n)
	}
	function It(t, n) {
		return t = +t, n = +n, function(e) {
			return Math.round(t * (1 - e) + n * e)
		}
	}
	var qt,
		Bt = 180 / Math.PI,
		Xt = {
			translateX: 0,
			translateY: 0,
			rotate: 0,
			skewX: 0,
			scaleX: 1,
			scaleY: 1
		};
	function Vt(t, n, e, r, i, a) {
		var o,
			u,
			l;
		return (o = Math.sqrt(t * t + n * n)) && (t /= o, n /= o), (l = t * e + n * r) && (e -= t * l, r -= n * l), (u = Math.sqrt(e * e + r * r)) && (e /= u, r /= u, l /= u), t * r < n * e && (t = -t, n = -n, l = -l, o = -o), {
			translateX: i,
			translateY: a,
			rotate: Math.atan2(n, t) * Bt,
			skewX: Math.atan(l) * Bt,
			scaleX: o,
			scaleY: u
		}
	}
	function Wt(t, n, e, r) {
		function i(t) {
			return t.length ? t.pop() + " " : ""
		}
		return function(a, o) {
			var u = [],
				l = [];
			return a = t(a), o = t(o), function(t, r, i, a, o, u) {
				if (t !== i || r !== a) {
					var l = o.push("translate(", null, n, null, e);
					u.push({
						i: l - 4,
						x: Rt(t, i)
					}, {
						i: l - 2,
						x: Rt(r, a)
					})
				} else
					(i || a) && o.push("translate(" + i + n + a + e)
			}(a.translateX, a.translateY, o.translateX, o.translateY, u, l), function(t, n, e, a) {
				t !== n ? (t - n > 180 ? n += 360 : n - t > 180 && (t += 360), a.push({
					i: e.push(i(e) + "rotate(", null, r) - 2,
					x: Rt(t, n)
				})) : n && e.push(i(e) + "rotate(" + n + r)
			}(a.rotate, o.rotate, u, l), function(t, n, e, a) {
				t !== n ? a.push({
					i: e.push(i(e) + "skewX(", null, r) - 2,
					x: Rt(t, n)
				}) : n && e.push(i(e) + "skewX(" + n + r)
			}(a.skewX, o.skewX, u, l), function(t, n, e, r, a, o) {
				if (t !== e || n !== r) {
					var u = a.push(i(a) + "scale(", null, ",", null, ")");
					o.push({
						i: u - 4,
						x: Rt(t, e)
					}, {
						i: u - 2,
						x: Rt(n, r)
					})
				} else
					1 === e && 1 === r || a.push(i(a) + "scale(" + e + "," + r + ")")
			}(a.scaleX, a.scaleY, o.scaleX, o.scaleY, u, l), a = o = null, function(t) {
				for (var n, e = -1, r = l.length; ++e < r;)
					u[(n = l[e]).i] = n.x(t);
				return u.join("")
			}
		}
	}
	var Gt = Wt((function(t) {
			const n = new ("function" == typeof DOMMatrix ? DOMMatrix : WebKitCSSMatrix)(t + "");
			return n.isIdentity ? Xt : Vt(n.a, n.b, n.c, n.d, n.e, n.f)
		}), "px, ", "px)", "deg)"),
		Zt = Wt((function(t) {
			return null == t ? Xt : (qt || (qt = document.createElementNS("http://www.w3.org/2000/svg", "g")), qt.setAttribute("transform", t), (t = qt.transform.baseVal.consolidate()) ? Vt((t = t.matrix).a, t.b, t.c, t.d, t.e, t.f) : Xt)
		}), ", ", ")", ")");
	function Qt(t) {
		return +t
	}
	var Jt = [0, 1];
	function Kt(t) {
		return t
	}
	function tn(t, n) {
		return (n -= t = +t) ? function(e) {
			return (e - t) / n
		} : (e = isNaN(n) ? NaN : .5, function() {
			return e
		});
		var e
	}
	function nn(t, n, e) {
		var r = t[0],
			i = t[1],
			a = n[0],
			o = n[1];
		return i < r ? (r = tn(i, r), a = e(o, a)) : (r = tn(r, i), a = e(a, o)), function(t) {
			return a(r(t))
		}
	}
	function en(t, n, e) {
		var r = Math.min(t.length, n.length) - 1,
			i = new Array(r),
			a = new Array(r),
			o = -1;
		for (t[r] < t[0] && (t = t.slice().reverse(), n = n.slice().reverse()); ++o < r;)
			i[o] = tn(t[o], t[o + 1]),
			a[o] = e(n[o], n[o + 1]);
		return function(n) {
			var e = d(t, n, 1, r) - 1;
			return a[e](i[e](n))
		}
	}
	function rn(t, n) {
		return n.domain(t.domain()).range(t.range()).interpolate(t.interpolate()).clamp(t.clamp()).unknown(t.unknown())
	}
	function an() {
		var t,
			n,
			e,
			r,
			i,
			a,
			o = Jt,
			u = Jt,
			l = $t,
			s = Kt;
		function c() {
			var t,
				n,
				e,
				l = Math.min(o.length, u.length);
			return s !== Kt && (t = o[0], n = o[l - 1], t > n && (e = t, t = n, n = e), s = function(e) {
				return Math.max(t, Math.min(n, e))
			}), r = l > 2 ? en : nn, i = a = null, f
		}
		function f(n) {
			return null == n || isNaN(n = +n) ? e : (i || (i = r(o.map(t), u, l)))(t(s(n)))
		}
		return f.invert = function(e) {
			return s(n((a || (a = r(u, o.map(t), Rt)))(e)))
		}, f.domain = function(t) {
			return arguments.length ? (o = Array.from(t, Qt), c()) : o.slice()
		}, f.range = function(t) {
			return arguments.length ? (u = Array.from(t), c()) : u.slice()
		}, f.rangeRound = function(t) {
			return u = Array.from(t), l = It, c()
		}, f.clamp = function(t) {
			return arguments.length ? (s = !!t || Kt, c()) : s !== Kt
		}, f.interpolate = function(t) {
			return arguments.length ? (l = t, c()) : l
		}, f.unknown = function(t) {
			return arguments.length ? (e = t, f) : e
		}, function(e, r) {
			return t = e, n = r, c()
		}
	}
	function on() {
		return an()(Kt, Kt)
	}
	function un(t, n) {
		if ((e = (t = n ? t.toExponential(n - 1) : t.toExponential()).indexOf("e")) < 0)
			return null;
		var e,
			r = t.slice(0, e);
		return [r.length > 1 ? r[0] + r.slice(2) : r, +t.slice(e + 1)]
	}
	function ln(t) {
		return (t = un(Math.abs(t))) ? t[1] : NaN
	}
	var sn,
		cn = /^(?:(.)?([<>=^]))?([+\-( ])?([$#])?(0)?(\d+)?(,)?(\.\d+)?(~)?([a-z%])?$/i;
	function fn(t) {
		if (!(n = cn.exec(t)))
			throw new Error("invalid format: " + t);
		var n;
		return new hn({
			fill: n[1],
			align: n[2],
			sign: n[3],
			symbol: n[4],
			zero: n[5],
			width: n[6],
			comma: n[7],
			precision: n[8] && n[8].slice(1),
			trim: n[9],
			type: n[10]
		})
	}
	function hn(t) {
		this.fill = void 0 === t.fill ? " " : t.fill + "",
		this.align = void 0 === t.align ? ">" : t.align + "",
		this.sign = void 0 === t.sign ? "-" : t.sign + "",
		this.symbol = void 0 === t.symbol ? "" : t.symbol + "",
		this.zero = !!t.zero,
		this.width = void 0 === t.width ? void 0 : +t.width,
		this.comma = !!t.comma,
		this.precision = void 0 === t.precision ? void 0 : +t.precision,
		this.trim = !!t.trim,
		this.type = void 0 === t.type ? "" : t.type + ""
	}
	function pn(t, n) {
		var e = un(t, n);
		if (!e)
			return t + "";
		var r = e[0],
			i = e[1];
		return i < 0 ? "0." + new Array(-i).join("0") + r : r.length > i + 1 ? r.slice(0, i + 1) + "." + r.slice(i + 1) : r + new Array(i - r.length + 2).join("0")
	}
	fn.prototype = hn.prototype,
	hn.prototype.toString = function() {
		return this.fill + this.align + this.sign + this.symbol + (this.zero ? "0" : "") + (void 0 === this.width ? "" : Math.max(1, 0 | this.width)) + (this.comma ? "," : "") + (void 0 === this.precision ? "" : "." + Math.max(0, 0 | this.precision)) + (this.trim ? "~" : "") + this.type
	};
	var gn = {
		"%": (t, n) => (100 * t).toFixed(n),
		b: t => Math.round(t).toString(2),
		c: t => t + "",
		d: function(t) {
			return Math.abs(t = Math.round(t)) >= 1e21 ? t.toLocaleString("en").replace(/,/g, "") : t.toString(10)
		},
		e: (t, n) => t.toExponential(n),
		f: (t, n) => t.toFixed(n),
		g: (t, n) => t.toPrecision(n),
		o: t => Math.round(t).toString(8),
		p: (t, n) => pn(100 * t, n),
		r: pn,
		s: function(t, n) {
			var e = un(t, n);
			if (!e)
				return t + "";
			var r = e[0],
				i = e[1],
				a = i - (sn = 3 * Math.max(-8, Math.min(8, Math.floor(i / 3)))) + 1,
				o = r.length;
			return a === o ? r : a > o ? r + new Array(a - o + 1).join("0") : a > 0 ? r.slice(0, a) + "." + r.slice(a) : "0." + new Array(1 - a).join("0") + un(t, Math.max(0, n + a - 1))[0]
		},
		X: t => Math.round(t).toString(16).toUpperCase(),
		x: t => Math.round(t).toString(16)
	};
	function dn(t) {
		return t
	}
	var mn,
		vn,
		yn,
		bn = Array.prototype.map,
		wn = ["y", "z", "a", "f", "p", "n", "µ", "m", "", "k", "M", "G", "T", "P", "E", "Z", "Y"];
	function _n(t) {
		var n,
			e,
			r = void 0 === t.grouping || void 0 === t.thousands ? dn : (n = bn.call(t.grouping, Number), e = t.thousands + "", function(t, r) {
				for (var i = t.length, a = [], o = 0, u = n[0], l = 0; i > 0 && u > 0 && (l + u + 1 > r && (u = Math.max(1, r - l)), a.push(t.substring(i -= u, i + u)), !((l += u + 1) > r));)
					u = n[o = (o + 1) % n.length];
				return a.reverse().join(e)
			}),
			i = void 0 === t.currency ? "" : t.currency[0] + "",
			a = void 0 === t.currency ? "" : t.currency[1] + "",
			o = void 0 === t.decimal ? "." : t.decimal + "",
			u = void 0 === t.numerals ? dn : function(t) {
				return function(n) {
					return n.replace(/[0-9]/g, (function(n) {
						return t[+n]
					}))
				}
			}(bn.call(t.numerals, String)),
			l = void 0 === t.percent ? "%" : t.percent + "",
			s = void 0 === t.minus ? "−" : t.minus + "",
			c = void 0 === t.nan ? "NaN" : t.nan + "";
		function f(t) {
			var n = (t = fn(t)).fill,
				e = t.align,
				f = t.sign,
				h = t.symbol,
				p = t.zero,
				g = t.width,
				d = t.comma,
				m = t.precision,
				v = t.trim,
				y = t.type;
			"n" === y ? (d = !0, y = "g") : gn[y] || (void 0 === m && (m = 12), v = !0, y = "g"),
			(p || "0" === n && "=" === e) && (p = !0, n = "0", e = "=");
			var b = "$" === h ? i : "#" === h && /[boxX]/.test(y) ? "0" + y.toLowerCase() : "",
				w = "$" === h ? a : /[%p]/.test(y) ? l : "",
				_ = gn[y],
				x = /[defgprs%]/.test(y);
			function M(t) {
				var i,
					a,
					l,
					h = b,
					M = w;
				if ("c" === y)
					M = _(t) + M,
					t = "";
				else {
					var A = (t = +t) < 0 || 1 / t < 0;
					if (t = isNaN(t) ? c : _(Math.abs(t), m), v && (t = function(t) {
						t:
						for (var n, e = t.length, r = 1, i = -1; r < e; ++r)
							switch (t[r]) {
							case ".":
								i = n = r;
								break;
							case "0":
								0 === i && (i = r),
								n = r;
								break;
							default:
								if (!+t[r])
									break t;
								i > 0 && (i = 0)
							}
						return i > 0 ? t.slice(0, i) + t.slice(n + 1) : t
					}(t)), A && 0 == +t && "+" !== f && (A = !1), h = (A ? "(" === f ? f : s : "-" === f || "(" === f ? "" : f) + h, M = ("s" === y ? wn[8 + sn / 3] : "") + M + (A && "(" === f ? ")" : ""), x)
						for (i = -1, a = t.length; ++i < a;)
							if (48 > (l = t.charCodeAt(i)) || l > 57) {
								M = (46 === l ? o + t.slice(i + 1) : t.slice(i)) + M,
								t = t.slice(0, i);
								break
							}
				}
				d && !p && (t = r(t, 1 / 0));
				var S = h.length + t.length + M.length,
					k = S < g ? new Array(g - S + 1).join(n) : "";
				switch (d && p && (t = r(k + t, k.length ? g - M.length : 1 / 0), k = ""), e) {
				case "<":
					t = h + t + M + k;
					break;
				case "=":
					t = h + k + t + M;
					break;
				case "^":
					t = k.slice(0, S = k.length >> 1) + h + t + M + k.slice(S);
					break;
				default:
					t = k + h + t + M
				}
				return u(t)
			}
			return m = void 0 === m ? 6 : /[gprs]/.test(y) ? Math.max(1, Math.min(21, m)) : Math.max(0, Math.min(20, m)), M.toString = function() {
				return t + ""
			}, M
		}
		return {
			format: f,
			formatPrefix: function(t, n) {
				var e = f(((t = fn(t)).type = "f", t)),
					r = 3 * Math.max(-8, Math.min(8, Math.floor(ln(n) / 3))),
					i = Math.pow(10, -r),
					a = wn[8 + r / 3];
				return function(t) {
					return e(i * t) + a
				}
			}
		}
	}
	function xn(t, n, e, r) {
		var i,
			a = A(t, n, e);
		switch ((r = fn(null == r ? ",f" : r)).type) {
		case "s":
			var o = Math.max(Math.abs(t), Math.abs(n));
			return null != r.precision || isNaN(i = function(t, n) {
				return Math.max(0, 3 * Math.max(-8, Math.min(8, Math.floor(ln(n) / 3))) - ln(Math.abs(t)))
			}(a, o)) || (r.precision = i), yn(r, o);
		case "":
		case "e":
		case "g":
		case "p":
		case "r":
			null != r.precision || isNaN(i = function(t, n) {
				return t = Math.abs(t), n = Math.abs(n) - t, Math.max(0, ln(n) - ln(t)) + 1
			}(a, Math.max(Math.abs(t), Math.abs(n)))) || (r.precision = i - ("e" === r.type));
			break;
		case "f":
		case "%":
			null != r.precision || isNaN(i = function(t) {
				return Math.max(0, -ln(Math.abs(t)))
			}(a)) || (r.precision = i - 2 * ("%" === r.type))
		}
		return vn(r)
	}
	function Mn(t) {
		var n = t.domain;
		return t.ticks = function(t) {
			var e = n();
			return function(t, n, e) {
				if (!((e = +e) > 0))
					return [];
				if ((t = +t) == (n = +n))
					return [t];
				const r = n < t,
					[i, a, o] = r ? x(n, t, e) : x(t, n, e);
				if (!(a >= i))
					return [];
				const u = a - i + 1,
					l = new Array(u);
				if (r)
					if (o < 0)
						for (let t = 0; t < u; ++t)
							l[t] = (a - t) / -o;
					else
						for (let t = 0; t < u; ++t)
							l[t] = (a - t) * o;
				else if (o < 0)
					for (let t = 0; t < u; ++t)
						l[t] = (i + t) / -o;
				else
					for (let t = 0; t < u; ++t)
						l[t] = (i + t) * o;
				return l
			}(e[0], e[e.length - 1], null == t ? 10 : t)
		}, t.tickFormat = function(t, e) {
			var r = n();
			return xn(r[0], r[r.length - 1], null == t ? 10 : t, e)
		}, t.nice = function(e) {
			null == e && (e = 10);
			var r,
				i,
				a = n(),
				o = 0,
				u = a.length - 1,
				l = a[o],
				s = a[u],
				c = 10;
			for (s < l && (i = l, l = s, s = i, i = o, o = u, u = i); c-- > 0;) {
				if ((i = M(l, s, e)) === r)
					return a[o] = l, a[u] = s, n(a);
				if (i > 0)
					l = Math.floor(l / i) * i,
					s = Math.ceil(s / i) * i;
				else {
					if (!(i < 0))
						break;
					l = Math.ceil(l * i) / i,
					s = Math.floor(s * i) / i
				}
				r = i
			}
			return t
		}, t
	}
	function An() {
		var t = on();
		return t.copy = function() {
			return rn(t, An())
		}, j.apply(t, arguments), Mn(t)
	}
	mn = _n({
		thousands: ",",
		grouping: [3],
		currency: ["$", ""]
	}),
	vn = mn.format,
	yn = mn.formatPrefix;
	const Sn = new Date,
		kn = new Date;
	function Cn(t, n, e, r) {
		function i(n) {
			return t(n = 0 === arguments.length ? new Date : new Date(+n)), n
		}
		return i.floor = n => (t(n = new Date(+n)), n), i.ceil = e => (t(e = new Date(e - 1)), n(e, 1), t(e), e), i.round = t => {
			const n = i(t),
				e = i.ceil(t);
			return t - n < e - t ? n : e
		}, i.offset = (t, e) => (n(t = new Date(+t), null == e ? 1 : Math.floor(e)), t), i.range = (e, r, a) => {
			const o = [];
			if (e = i.ceil(e), a = null == a ? 1 : Math.floor(a), !(e < r && a > 0))
				return o;
			let u;
			do {
				o.push(u = new Date(+e)),
				n(e, a),
				t(e)
			} while (u < e && e < r);
			return o
		}, i.filter = e => Cn((n => {
			if (n >= n)
				for (; t(n), !e(n);)
					n.setTime(n - 1)
		}), ((t, r) => {
			if (t >= t)
				if (r < 0)
					for (; ++r <= 0;)
						for (; n(t, -1), !e(t);)
							;
				else
					for (; --r >= 0;)
						for (; n(t, 1), !e(t);)
							;
		})), e && (i.count = (n, r) => (Sn.setTime(+n), kn.setTime(+r), t(Sn), t(kn), Math.floor(e(Sn, kn))), i.every = t => (t = Math.floor(t), isFinite(t) && t > 0 ? t > 1 ? i.filter(r ? n => r(n) % t == 0 : n => i.count(0, n) % t == 0) : i : null)), i
	}
	const Tn = Cn((() => {}), ((t, n) => {
		t.setTime(+t + n)
	}), ((t, n) => n - t));
	Tn.every = t => (t = Math.floor(t), isFinite(t) && t > 0 ? t > 1 ? Cn((n => {
		n.setTime(Math.floor(n / t) * t)
	}), ((n, e) => {
		n.setTime(+n + e * t)
	}), ((n, e) => (e - n) / t)) : Tn : null),
	Tn.range;
	const Dn = 1e3,
		Nn = 60 * Dn,
		zn = 60 * Nn,
		En = 24 * zn,
		Fn = 7 * En,
		Hn = 30 * En,
		Ln = 365 * En,
		Un = Cn((t => {
			t.setTime(t - t.getMilliseconds())
		}), ((t, n) => {
			t.setTime(+t + n * Dn)
		}), ((t, n) => (n - t) / Dn), (t => t.getUTCSeconds()));
	Un.range;
	const Rn = Cn((t => {
		t.setTime(t - t.getMilliseconds() - t.getSeconds() * Dn)
	}), ((t, n) => {
		t.setTime(+t + n * Nn)
	}), ((t, n) => (n - t) / Nn), (t => t.getMinutes()));
	Rn.range;
	const Yn = Cn((t => {
		t.setUTCSeconds(0, 0)
	}), ((t, n) => {
		t.setTime(+t + n * Nn)
	}), ((t, n) => (n - t) / Nn), (t => t.getUTCMinutes()));
	Yn.range;
	const On = Cn((t => {
		t.setTime(t - t.getMilliseconds() - t.getSeconds() * Dn - t.getMinutes() * Nn)
	}), ((t, n) => {
		t.setTime(+t + n * zn)
	}), ((t, n) => (n - t) / zn), (t => t.getHours()));
	On.range;
	const Pn = Cn((t => {
		t.setUTCMinutes(0, 0, 0)
	}), ((t, n) => {
		t.setTime(+t + n * zn)
	}), ((t, n) => (n - t) / zn), (t => t.getUTCHours()));
	Pn.range;
	const jn = Cn((t => t.setHours(0, 0, 0, 0)), ((t, n) => t.setDate(t.getDate() + n)), ((t, n) => (n - t - (n.getTimezoneOffset() - t.getTimezoneOffset()) * Nn) / En), (t => t.getDate() - 1));
	jn.range;
	const $n = Cn((t => {
		t.setUTCHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setUTCDate(t.getUTCDate() + n)
	}), ((t, n) => (n - t) / En), (t => t.getUTCDate() - 1));
	$n.range;
	const In = Cn((t => {
		t.setUTCHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setUTCDate(t.getUTCDate() + n)
	}), ((t, n) => (n - t) / En), (t => Math.floor(t / En)));
	function qn(t) {
		return Cn((n => {
			n.setDate(n.getDate() - (n.getDay() + 7 - t) % 7),
			n.setHours(0, 0, 0, 0)
		}), ((t, n) => {
			t.setDate(t.getDate() + 7 * n)
		}), ((t, n) => (n - t - (n.getTimezoneOffset() - t.getTimezoneOffset()) * Nn) / Fn))
	}
	In.range;
	const Bn = qn(0),
		Xn = qn(1),
		Vn = qn(2),
		Wn = qn(3),
		Gn = qn(4),
		Zn = qn(5),
		Qn = qn(6);
	function Jn(t) {
		return Cn((n => {
			n.setUTCDate(n.getUTCDate() - (n.getUTCDay() + 7 - t) % 7),
			n.setUTCHours(0, 0, 0, 0)
		}), ((t, n) => {
			t.setUTCDate(t.getUTCDate() + 7 * n)
		}), ((t, n) => (n - t) / Fn))
	}
	Bn.range,
	Xn.range,
	Vn.range,
	Wn.range,
	Gn.range,
	Zn.range,
	Qn.range;
	const Kn = Jn(0),
		te = Jn(1),
		ne = Jn(2),
		ee = Jn(3),
		re = Jn(4),
		ie = Jn(5),
		ae = Jn(6);
	Kn.range,
	te.range,
	ne.range,
	ee.range,
	re.range,
	ie.range,
	ae.range;
	const oe = Cn((t => {
		t.setDate(1),
		t.setHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setMonth(t.getMonth() + n)
	}), ((t, n) => n.getMonth() - t.getMonth() + 12 * (n.getFullYear() - t.getFullYear())), (t => t.getMonth()));
	oe.range;
	const ue = Cn((t => {
		t.setUTCDate(1),
		t.setUTCHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setUTCMonth(t.getUTCMonth() + n)
	}), ((t, n) => n.getUTCMonth() - t.getUTCMonth() + 12 * (n.getUTCFullYear() - t.getUTCFullYear())), (t => t.getUTCMonth()));
	ue.range;
	const le = Cn((t => {
		t.setMonth(0, 1),
		t.setHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setFullYear(t.getFullYear() + n)
	}), ((t, n) => n.getFullYear() - t.getFullYear()), (t => t.getFullYear()));
	le.every = t => isFinite(t = Math.floor(t)) && t > 0 ? Cn((n => {
		n.setFullYear(Math.floor(n.getFullYear() / t) * t),
		n.setMonth(0, 1),
		n.setHours(0, 0, 0, 0)
	}), ((n, e) => {
		n.setFullYear(n.getFullYear() + e * t)
	})) : null,
	le.range;
	const se = Cn((t => {
		t.setUTCMonth(0, 1),
		t.setUTCHours(0, 0, 0, 0)
	}), ((t, n) => {
		t.setUTCFullYear(t.getUTCFullYear() + n)
	}), ((t, n) => n.getUTCFullYear() - t.getUTCFullYear()), (t => t.getUTCFullYear()));
	function ce(t, n, e, r, i, a) {
		const o = [[Un, 1, Dn], [Un, 5, 5 * Dn], [Un, 15, 15 * Dn], [Un, 30, 30 * Dn], [a, 1, Nn], [a, 5, 5 * Nn], [a, 15, 15 * Nn], [a, 30, 30 * Nn], [i, 1, zn], [i, 3, 3 * zn], [i, 6, 6 * zn], [i, 12, 12 * zn], [r, 1, En], [r, 2, 2 * En], [e, 1, Fn], [n, 1, Hn], [n, 3, 3 * Hn], [t, 1, Ln]];
		function u(n, e, r) {
			const i = Math.abs(e - n) / r,
				a = h((([, , t]) => t)).right(o, i);
			if (a === o.length)
				return t.every(A(n / Ln, e / Ln, r));
			if (0 === a)
				return Tn.every(Math.max(A(n, e, r), 1));
			const [u, l] = o[i / o[a - 1][2] < o[a][2] / i ? a - 1 : a];
			return u.every(l)
		}
		return [function(t, n, e) {
			const r = n < t;
			r && ([t, n] = [n, t]);
			const i = e && "function" == typeof e.range ? e : u(t, n, e),
				a = i ? i.range(t, +n + 1) : [];
			return r ? a.reverse() : a
		}, u]
	}
	se.every = t => isFinite(t = Math.floor(t)) && t > 0 ? Cn((n => {
		n.setUTCFullYear(Math.floor(n.getUTCFullYear() / t) * t),
		n.setUTCMonth(0, 1),
		n.setUTCHours(0, 0, 0, 0)
	}), ((n, e) => {
		n.setUTCFullYear(n.getUTCFullYear() + e * t)
	})) : null,
	se.range;
	const [fe, he] = ce(se, ue, Kn, In, Pn, Yn),
		[pe, ge] = ce(le, oe, Bn, jn, On, Rn);
	function de(t) {
		if (0 <= t.y && t.y < 100) {
			var n = new Date(-1, t.m, t.d, t.H, t.M, t.S, t.L);
			return n.setFullYear(t.y), n
		}
		return new Date(t.y, t.m, t.d, t.H, t.M, t.S, t.L)
	}
	function me(t) {
		if (0 <= t.y && t.y < 100) {
			var n = new Date(Date.UTC(-1, t.m, t.d, t.H, t.M, t.S, t.L));
			return n.setUTCFullYear(t.y), n
		}
		return new Date(Date.UTC(t.y, t.m, t.d, t.H, t.M, t.S, t.L))
	}
	function ve(t, n, e) {
		return {
			y: t,
			m: n,
			d: e,
			H: 0,
			M: 0,
			S: 0,
			L: 0
		}
	}
	var ye,
		be,
		we,
		_e = {
			"-": "",
			_: " ",
			0: "0"
		},
		xe = /^\s*\d+/,
		Me = /^%/,
		Ae = /[\\^$*+?|[\]().{}]/g;
	function Se(t, n, e) {
		var r = t < 0 ? "-" : "",
			i = (r ? -t : t) + "",
			a = i.length;
		return r + (a < e ? new Array(e - a + 1).join(n) + i : i)
	}
	function ke(t) {
		return t.replace(Ae, "\\$&")
	}
	function Ce(t) {
		return new RegExp("^(?:" + t.map(ke).join("|") + ")", "i")
	}
	function Te(t) {
		return new Map(t.map(((t, n) => [t.toLowerCase(), n])))
	}
	function De(t, n, e) {
		var r = xe.exec(n.slice(e, e + 1));
		return r ? (t.w = +r[0], e + r[0].length) : -1
	}
	function Ne(t, n, e) {
		var r = xe.exec(n.slice(e, e + 1));
		return r ? (t.u = +r[0], e + r[0].length) : -1
	}
	function ze(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.U = +r[0], e + r[0].length) : -1
	}
	function Ee(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.V = +r[0], e + r[0].length) : -1
	}
	function Fe(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.W = +r[0], e + r[0].length) : -1
	}
	function He(t, n, e) {
		var r = xe.exec(n.slice(e, e + 4));
		return r ? (t.y = +r[0], e + r[0].length) : -1
	}
	function Le(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.y = +r[0] + (+r[0] > 68 ? 1900 : 2e3), e + r[0].length) : -1
	}
	function Ue(t, n, e) {
		var r = /^(Z)|([+-]\d\d)(?::?(\d\d))?/.exec(n.slice(e, e + 6));
		return r ? (t.Z = r[1] ? 0 : -(r[2] + (r[3] || "00")), e + r[0].length) : -1
	}
	function Re(t, n, e) {
		var r = xe.exec(n.slice(e, e + 1));
		return r ? (t.q = 3 * r[0] - 3, e + r[0].length) : -1
	}
	function Ye(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.m = r[0] - 1, e + r[0].length) : -1
	}
	function Oe(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.d = +r[0], e + r[0].length) : -1
	}
	function Pe(t, n, e) {
		var r = xe.exec(n.slice(e, e + 3));
		return r ? (t.m = 0, t.d = +r[0], e + r[0].length) : -1
	}
	function je(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.H = +r[0], e + r[0].length) : -1
	}
	function $e(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.M = +r[0], e + r[0].length) : -1
	}
	function Ie(t, n, e) {
		var r = xe.exec(n.slice(e, e + 2));
		return r ? (t.S = +r[0], e + r[0].length) : -1
	}
	function qe(t, n, e) {
		var r = xe.exec(n.slice(e, e + 3));
		return r ? (t.L = +r[0], e + r[0].length) : -1
	}
	function Be(t, n, e) {
		var r = xe.exec(n.slice(e, e + 6));
		return r ? (t.L = Math.floor(r[0] / 1e3), e + r[0].length) : -1
	}
	function Xe(t, n, e) {
		var r = Me.exec(n.slice(e, e + 1));
		return r ? e + r[0].length : -1
	}
	function Ve(t, n, e) {
		var r = xe.exec(n.slice(e));
		return r ? (t.Q = +r[0], e + r[0].length) : -1
	}
	function We(t, n, e) {
		var r = xe.exec(n.slice(e));
		return r ? (t.s = +r[0], e + r[0].length) : -1
	}
	function Ge(t, n) {
		return Se(t.getDate(), n, 2)
	}
	function Ze(t, n) {
		return Se(t.getHours(), n, 2)
	}
	function Qe(t, n) {
		return Se(t.getHours() % 12 || 12, n, 2)
	}
	function Je(t, n) {
		return Se(1 + jn.count(le(t), t), n, 3)
	}
	function Ke(t, n) {
		return Se(t.getMilliseconds(), n, 3)
	}
	function tr(t, n) {
		return Ke(t, n) + "000"
	}
	function nr(t, n) {
		return Se(t.getMonth() + 1, n, 2)
	}
	function er(t, n) {
		return Se(t.getMinutes(), n, 2)
	}
	function rr(t, n) {
		return Se(t.getSeconds(), n, 2)
	}
	function ir(t) {
		var n = t.getDay();
		return 0 === n ? 7 : n
	}
	function ar(t, n) {
		return Se(Bn.count(le(t) - 1, t), n, 2)
	}
	function or(t) {
		var n = t.getDay();
		return n >= 4 || 0 === n ? Gn(t) : Gn.ceil(t)
	}
	function ur(t, n) {
		return t = or(t), Se(Gn.count(le(t), t) + (4 === le(t).getDay()), n, 2)
	}
	function lr(t) {
		return t.getDay()
	}
	function sr(t, n) {
		return Se(Xn.count(le(t) - 1, t), n, 2)
	}
	function cr(t, n) {
		return Se(t.getFullYear() % 100, n, 2)
	}
	function fr(t, n) {
		return Se((t = or(t)).getFullYear() % 100, n, 2)
	}
	function hr(t, n) {
		return Se(t.getFullYear() % 1e4, n, 4)
	}
	function pr(t, n) {
		var e = t.getDay();
		return Se((t = e >= 4 || 0 === e ? Gn(t) : Gn.ceil(t)).getFullYear() % 1e4, n, 4)
	}
	function gr(t) {
		var n = t.getTimezoneOffset();
		return (n > 0 ? "-" : (n *= -1, "+")) + Se(n / 60 | 0, "0", 2) + Se(n % 60, "0", 2)
	}
	function dr(t, n) {
		return Se(t.getUTCDate(), n, 2)
	}
	function mr(t, n) {
		return Se(t.getUTCHours(), n, 2)
	}
	function vr(t, n) {
		return Se(t.getUTCHours() % 12 || 12, n, 2)
	}
	function yr(t, n) {
		return Se(1 + $n.count(se(t), t), n, 3)
	}
	function br(t, n) {
		return Se(t.getUTCMilliseconds(), n, 3)
	}
	function wr(t, n) {
		return br(t, n) + "000"
	}
	function _r(t, n) {
		return Se(t.getUTCMonth() + 1, n, 2)
	}
	function xr(t, n) {
		return Se(t.getUTCMinutes(), n, 2)
	}
	function Mr(t, n) {
		return Se(t.getUTCSeconds(), n, 2)
	}
	function Ar(t) {
		var n = t.getUTCDay();
		return 0 === n ? 7 : n
	}
	function Sr(t, n) {
		return Se(Kn.count(se(t) - 1, t), n, 2)
	}
	function kr(t) {
		var n = t.getUTCDay();
		return n >= 4 || 0 === n ? re(t) : re.ceil(t)
	}
	function Cr(t, n) {
		return t = kr(t), Se(re.count(se(t), t) + (4 === se(t).getUTCDay()), n, 2)
	}
	function Tr(t) {
		return t.getUTCDay()
	}
	function Dr(t, n) {
		return Se(te.count(se(t) - 1, t), n, 2)
	}
	function Nr(t, n) {
		return Se(t.getUTCFullYear() % 100, n, 2)
	}
	function zr(t, n) {
		return Se((t = kr(t)).getUTCFullYear() % 100, n, 2)
	}
	function Er(t, n) {
		return Se(t.getUTCFullYear() % 1e4, n, 4)
	}
	function Fr(t, n) {
		var e = t.getUTCDay();
		return Se((t = e >= 4 || 0 === e ? re(t) : re.ceil(t)).getUTCFullYear() % 1e4, n, 4)
	}
	function Hr() {
		return "+0000"
	}
	function Lr() {
		return "%"
	}
	function Ur(t) {
		return +t
	}
	function Rr(t) {
		return Math.floor(+t / 1e3)
	}
	function Yr(t) {
		return new Date(t)
	}
	function Or(t) {
		return t instanceof Date ? +t : +new Date(+t)
	}
	function Pr(t, n, e, r, i, a, o, u, l, s) {
		var c = on(),
			f = c.invert,
			h = c.domain,
			p = s(".%L"),
			g = s(":%S"),
			d = s("%I:%M"),
			m = s("%I %p"),
			v = s("%a %d"),
			y = s("%b %d"),
			b = s("%B"),
			w = s("%Y");
		function _(t) {
			return (l(t) < t ? p : u(t) < t ? g : o(t) < t ? d : a(t) < t ? m : r(t) < t ? i(t) < t ? v : y : e(t) < t ? b : w)(t)
		}
		return c.invert = function(t) {
			return new Date(f(t))
		}, c.domain = function(t) {
			return arguments.length ? h(Array.from(t, Or)) : h().map(Yr)
		}, c.ticks = function(n) {
			var e = h();
			return t(e[0], e[e.length - 1], null == n ? 10 : n)
		}, c.tickFormat = function(t, n) {
			return null == n ? _ : s(n)
		}, c.nice = function(t) {
			var e = h();
			return t && "function" == typeof t.range || (t = n(e[0], e[e.length - 1], null == t ? 10 : t)), t ? h(function(t, n) {
				var e,
					r = 0,
					i = (t = t.slice()).length - 1,
					a = t[r],
					o = t[i];
				return o < a && (e = r, r = i, i = e, e = a, a = o, o = e), t[r] = n.floor(a), t[i] = n.ceil(o), t
			}(e, t)) : c
		}, c.copy = function() {
			return rn(c, Pr(t, n, e, r, i, a, o, u, l, s))
		}, c
	}
	function jr() {
		return j.apply(Pr(pe, ge, le, oe, Bn, jn, On, Rn, Un, be).domain([new Date(2e3, 0, 1), new Date(2e3, 0, 2)]), arguments)
	}
	function $r() {
		return j.apply(Pr(fe, he, se, ue, Kn, $n, Pn, Yn, Un, we).domain([Date.UTC(2e3, 0, 1), Date.UTC(2e3, 0, 2)]), arguments)
	}
	function Ir() {
		var t = Mn(function() {
			var t,
				n,
				e,
				r,
				i,
				a = 0,
				o = 1,
				u = Kt,
				l = !1;
			function s(n) {
				return null == n || isNaN(n = +n) ? i : u(0 === e ? .5 : (n = (r(n) - t) * e, l ? Math.max(0, Math.min(1, n)) : n))
			}
			function c(t) {
				return function(n) {
					var e,
						r;
					return arguments.length ? ([e, r] = n, u = t(e, r), s) : [u(0), u(1)]
				}
			}
			return s.domain = function(i) {
				return arguments.length ? ([a, o] = i, t = r(a = +a), n = r(o = +o), e = t === n ? 0 : 1 / (n - t), s) : [a, o]
			}, s.clamp = function(t) {
				return arguments.length ? (l = !!t, s) : l
			}, s.interpolator = function(t) {
				return arguments.length ? (u = t, s) : u
			}, s.range = c($t), s.rangeRound = c(It), s.unknown = function(t) {
				return arguments.length ? (i = t, s) : i
			}, function(i) {
				return r = i, t = i(a), n = i(o), e = t === n ? 0 : 1 / (n - t), s
			}
		}()(Kt));
		return t.copy = function() {
			return n = t, Ir().domain(n.domain()).interpolator(n.interpolator()).clamp(n.clamp()).unknown(n.unknown());
			var n
		}, $.apply(t, arguments)
	}
	!function(t) {
		ye = function(t) {
			var n = t.dateTime,
				e = t.date,
				r = t.time,
				i = t.periods,
				a = t.days,
				o = t.shortDays,
				u = t.months,
				l = t.shortMonths,
				s = Ce(i),
				c = Te(i),
				f = Ce(a),
				h = Te(a),
				p = Ce(o),
				g = Te(o),
				d = Ce(u),
				m = Te(u),
				v = Ce(l),
				y = Te(l),
				b = {
					a: function(t) {
						return o[t.getDay()]
					},
					A: function(t) {
						return a[t.getDay()]
					},
					b: function(t) {
						return l[t.getMonth()]
					},
					B: function(t) {
						return u[t.getMonth()]
					},
					c: null,
					d: Ge,
					e: Ge,
					f: tr,
					g: fr,
					G: pr,
					H: Ze,
					I: Qe,
					j: Je,
					L: Ke,
					m: nr,
					M: er,
					p: function(t) {
						return i[+(t.getHours() >= 12)]
					},
					q: function(t) {
						return 1 + ~~(t.getMonth() / 3)
					},
					Q: Ur,
					s: Rr,
					S: rr,
					u: ir,
					U: ar,
					V: ur,
					w: lr,
					W: sr,
					x: null,
					X: null,
					y: cr,
					Y: hr,
					Z: gr,
					"%": Lr
				},
				w = {
					a: function(t) {
						return o[t.getUTCDay()]
					},
					A: function(t) {
						return a[t.getUTCDay()]
					},
					b: function(t) {
						return l[t.getUTCMonth()]
					},
					B: function(t) {
						return u[t.getUTCMonth()]
					},
					c: null,
					d: dr,
					e: dr,
					f: wr,
					g: zr,
					G: Fr,
					H: mr,
					I: vr,
					j: yr,
					L: br,
					m: _r,
					M: xr,
					p: function(t) {
						return i[+(t.getUTCHours() >= 12)]
					},
					q: function(t) {
						return 1 + ~~(t.getUTCMonth() / 3)
					},
					Q: Ur,
					s: Rr,
					S: Mr,
					u: Ar,
					U: Sr,
					V: Cr,
					w: Tr,
					W: Dr,
					x: null,
					X: null,
					y: Nr,
					Y: Er,
					Z: Hr,
					"%": Lr
				},
				_ = {
					a: function(t, n, e) {
						var r = p.exec(n.slice(e));
						return r ? (t.w = g.get(r[0].toLowerCase()), e + r[0].length) : -1
					},
					A: function(t, n, e) {
						var r = f.exec(n.slice(e));
						return r ? (t.w = h.get(r[0].toLowerCase()), e + r[0].length) : -1
					},
					b: function(t, n, e) {
						var r = v.exec(n.slice(e));
						return r ? (t.m = y.get(r[0].toLowerCase()), e + r[0].length) : -1
					},
					B: function(t, n, e) {
						var r = d.exec(n.slice(e));
						return r ? (t.m = m.get(r[0].toLowerCase()), e + r[0].length) : -1
					},
					c: function(t, e, r) {
						return A(t, n, e, r)
					},
					d: Oe,
					e: Oe,
					f: Be,
					g: Le,
					G: He,
					H: je,
					I: je,
					j: Pe,
					L: qe,
					m: Ye,
					M: $e,
					p: function(t, n, e) {
						var r = s.exec(n.slice(e));
						return r ? (t.p = c.get(r[0].toLowerCase()), e + r[0].length) : -1
					},
					q: Re,
					Q: Ve,
					s: We,
					S: Ie,
					u: Ne,
					U: ze,
					V: Ee,
					w: De,
					W: Fe,
					x: function(t, n, r) {
						return A(t, e, n, r)
					},
					X: function(t, n, e) {
						return A(t, r, n, e)
					},
					y: Le,
					Y: He,
					Z: Ue,
					"%": Xe
				};
			function x(t, n) {
				return function(e) {
					var r,
						i,
						a,
						o = [],
						u = -1,
						l = 0,
						s = t.length;
					for (e instanceof Date || (e = new Date(+e)); ++u < s;)
						37 === t.charCodeAt(u) && (o.push(t.slice(l, u)), null != (i = _e[r = t.charAt(++u)]) ? r = t.charAt(++u) : i = "e" === r ? " " : "0", (a = n[r]) && (r = a(e, i)), o.push(r), l = u + 1);
					return o.push(t.slice(l, u)), o.join("")
				}
			}
			function M(t, n) {
				return function(e) {
					var r,
						i,
						a = ve(1900, void 0, 1);
					if (A(a, t, e += "", 0) != e.length)
						return null;
					if ("Q" in a)
						return new Date(a.Q);
					if ("s" in a)
						return new Date(1e3 * a.s + ("L" in a ? a.L : 0));
					if (n && !("Z" in a) && (a.Z = 0), "p" in a && (a.H = a.H % 12 + 12 * a.p), void 0 === a.m && (a.m = "q" in a ? a.q : 0), "V" in a) {
						if (a.V < 1 || a.V > 53)
							return null;
						"w" in a || (a.w = 1),
						"Z" in a ? (i = (r = me(ve(a.y, 0, 1))).getUTCDay(), r = i > 4 || 0 === i ? te.ceil(r) : te(r), r = $n.offset(r, 7 * (a.V - 1)), a.y = r.getUTCFullYear(), a.m = r.getUTCMonth(), a.d = r.getUTCDate() + (a.w + 6) % 7) : (i = (r = de(ve(a.y, 0, 1))).getDay(), r = i > 4 || 0 === i ? Xn.ceil(r) : Xn(r), r = jn.offset(r, 7 * (a.V - 1)), a.y = r.getFullYear(), a.m = r.getMonth(), a.d = r.getDate() + (a.w + 6) % 7)
					} else
						("W" in a || "U" in a) && ("w" in a || (a.w = "u" in a ? a.u % 7 : "W" in a ? 1 : 0), i = "Z" in a ? me(ve(a.y, 0, 1)).getUTCDay() : de(ve(a.y, 0, 1)).getDay(), a.m = 0, a.d = "W" in a ? (a.w + 6) % 7 + 7 * a.W - (i + 5) % 7 : a.w + 7 * a.U - (i + 6) % 7);
					return "Z" in a ? (a.H += a.Z / 100 | 0, a.M += a.Z % 100, me(a)) : de(a)
				}
			}
			function A(t, n, e, r) {
				for (var i, a, o = 0, u = n.length, l = e.length; o < u;) {
					if (r >= l)
						return -1;
					if (37 === (i = n.charCodeAt(o++))) {
						if (i = n.charAt(o++), !(a = _[i in _e ? n.charAt(o++) : i]) || (r = a(t, e, r)) < 0)
							return -1
					} else if (i != e.charCodeAt(r++))
						return -1
				}
				return r
			}
			return b.x = x(e, b), b.X = x(r, b), b.c = x(n, b), w.x = x(e, w), w.X = x(r, w), w.c = x(n, w), {
				format: function(t) {
					var n = x(t += "", b);
					return n.toString = function() {
						return t
					}, n
				},
				parse: function(t) {
					var n = M(t += "", !1);
					return n.toString = function() {
						return t
					}, n
				},
				utcFormat: function(t) {
					var n = x(t += "", w);
					return n.toString = function() {
						return t
					}, n
				},
				utcParse: function(t) {
					var n = M(t += "", !0);
					return n.toString = function() {
						return t
					}, n
				}
			}
		}(t),
		be = ye.format,
		ye.parse,
		we = ye.utcFormat,
		ye.utcParse
	}({
		dateTime: "%x, %X",
		date: "%-m/%-d/%Y",
		time: "%-I:%M:%S %p",
		periods: ["AM", "PM"],
		days: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
		shortDays: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
		months: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
		shortMonths: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
	});
	var qr = "http://www.w3.org/1999/xhtml",
		Br = {
			svg: "http://www.w3.org/2000/svg",
			xhtml: qr,
			xlink: "http://www.w3.org/1999/xlink",
			xml: "http://www.w3.org/XML/1998/namespace",
			xmlns: "http://www.w3.org/2000/xmlns/"
		};
	function Xr(t) {
		var n = t += "",
			e = n.indexOf(":");
		return e >= 0 && "xmlns" !== (n = t.slice(0, e)) && (t = t.slice(e + 1)), Br.hasOwnProperty(n) ? {
			space: Br[n],
			local: t
		} : t
	}
	function Vr(t) {
		return function() {
			var n = this.ownerDocument,
				e = this.namespaceURI;
			return e === qr && n.documentElement.namespaceURI === qr ? n.createElement(t) : n.createElementNS(e, t)
		}
	}
	function Wr(t) {
		return function() {
			return this.ownerDocument.createElementNS(t.space, t.local)
		}
	}
	function Gr(t) {
		var n = Xr(t);
		return (n.local ? Wr : Vr)(n)
	}
	function Zr() {}
	function Qr(t) {
		return null == t ? Zr : function() {
			return this.querySelector(t)
		}
	}
	function Jr() {
		return []
	}
	function Kr(t) {
		return null == t ? Jr : function() {
			return this.querySelectorAll(t)
		}
	}
	function ti(t) {
		return function() {
			return null == (n = t.apply(this, arguments)) ? [] : Array.isArray(n) ? n : Array.from(n);
			var n
		}
	}
	function ni(t) {
		return function() {
			return this.matches(t)
		}
	}
	function ei(t) {
		return function(n) {
			return n.matches(t)
		}
	}
	var ri = Array.prototype.find;
	function ii() {
		return this.firstElementChild
	}
	var ai = Array.prototype.filter;
	function oi() {
		return Array.from(this.children)
	}
	function ui(t) {
		return new Array(t.length)
	}
	function li(t, n) {
		this.ownerDocument = t.ownerDocument,
		this.namespaceURI = t.namespaceURI,
		this._next = null,
		this._parent = t,
		this.__data__ = n
	}
	function si(t, n, e, r, i, a) {
		for (var o, u = 0, l = n.length, s = a.length; u < s; ++u)
			(o = n[u]) ? (o.__data__ = a[u], r[u] = o) : e[u] = new li(t, a[u]);
		for (; u < l; ++u)
			(o = n[u]) && (i[u] = o)
	}
	function ci(t, n, e, r, i, a, o) {
		var u,
			l,
			s,
			c = new Map,
			f = n.length,
			h = a.length,
			p = new Array(f);
		for (u = 0; u < f; ++u)
			(l = n[u]) && (p[u] = s = o.call(l, l.__data__, u, n) + "", c.has(s) ? i[u] = l : c.set(s, l));
		for (u = 0; u < h; ++u)
			s = o.call(t, a[u], u, a) + "",
			(l = c.get(s)) ? (r[u] = l, l.__data__ = a[u], c.delete(s)) : e[u] = new li(t, a[u]);
		for (u = 0; u < f; ++u)
			(l = n[u]) && c.get(p[u]) === l && (i[u] = l)
	}
	function fi(t) {
		return t.__data__
	}
	function hi(t) {
		return "object" == typeof t && "length" in t ? t : Array.from(t)
	}
	function pi(t, n) {
		return t < n ? -1 : t > n ? 1 : t >= n ? 0 : NaN
	}
	function gi(t) {
		return function() {
			this.removeAttribute(t)
		}
	}
	function di(t) {
		return function() {
			this.removeAttributeNS(t.space, t.local)
		}
	}
	function mi(t, n) {
		return function() {
			this.setAttribute(t, n)
		}
	}
	function vi(t, n) {
		return function() {
			this.setAttributeNS(t.space, t.local, n)
		}
	}
	function yi(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttribute(t) : this.setAttribute(t, e)
		}
	}
	function bi(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttributeNS(t.space, t.local) : this.setAttributeNS(t.space, t.local, e)
		}
	}
	function wi(t) {
		return t.ownerDocument && t.ownerDocument.defaultView || t.document && t || t.defaultView
	}
	function _i(t) {
		return function() {
			this.style.removeProperty(t)
		}
	}
	function xi(t, n, e) {
		return function() {
			this.style.setProperty(t, n, e)
		}
	}
	function Mi(t, n, e) {
		return function() {
			var r = n.apply(this, arguments);
			null == r ? this.style.removeProperty(t) : this.style.setProperty(t, r, e)
		}
	}
	function Ai(t, n) {
		return t.style.getPropertyValue(n) || wi(t).getComputedStyle(t, null).getPropertyValue(n)
	}
	function Si(t) {
		return function() {
			delete this[t]
		}
	}
	function ki(t, n) {
		return function() {
			this[t] = n
		}
	}
	function Ci(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? delete this[t] : this[t] = e
		}
	}
	function Ti(t) {
		return t.trim().split(/^|\s+/)
	}
	function Di(t) {
		return t.classList || new Ni(t)
	}
	function Ni(t) {
		this._node = t,
		this._names = Ti(t.getAttribute("class") || "")
	}
	function zi(t, n) {
		for (var e = Di(t), r = -1, i = n.length; ++r < i;)
			e.add(n[r])
	}
	function Ei(t, n) {
		for (var e = Di(t), r = -1, i = n.length; ++r < i;)
			e.remove(n[r])
	}
	function Fi(t) {
		return function() {
			zi(this, t)
		}
	}
	function Hi(t) {
		return function() {
			Ei(this, t)
		}
	}
	function Li(t, n) {
		return function() {
			(n.apply(this, arguments) ? zi : Ei)(this, t)
		}
	}
	function Ui() {
		this.textContent = ""
	}
	function Ri(t) {
		return function() {
			this.textContent = t
		}
	}
	function Yi(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.textContent = null == n ? "" : n
		}
	}
	function Oi() {
		this.innerHTML = ""
	}
	function Pi(t) {
		return function() {
			this.innerHTML = t
		}
	}
	function ji(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.innerHTML = null == n ? "" : n
		}
	}
	function $i() {
		this.nextSibling && this.parentNode.appendChild(this)
	}
	function Ii() {
		this.previousSibling && this.parentNode.insertBefore(this, this.parentNode.firstChild)
	}
	function qi() {
		return null
	}
	function Bi() {
		var t = this.parentNode;
		t && t.removeChild(this)
	}
	function Xi() {
		var t = this.cloneNode(!1),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	function Vi() {
		var t = this.cloneNode(!0),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	function Wi(t) {
		return function() {
			var n = this.__on;
			if (n) {
				for (var e, r = 0, i = -1, a = n.length; r < a; ++r)
					e = n[r],
					t.type && e.type !== t.type || e.name !== t.name ? n[++i] = e : this.removeEventListener(e.type, e.listener, e.options);
				++i ? n.length = i : delete this.__on
			}
		}
	}
	function Gi(t, n, e) {
		return function() {
			var r,
				i = this.__on,
				a = function(t) {
					return function(n) {
						t.call(this, n, this.__data__)
					}
				}(n);
			if (i)
				for (var o = 0, u = i.length; o < u; ++o)
					if ((r = i[o]).type === t.type && r.name === t.name)
						return this.removeEventListener(r.type, r.listener, r.options), this.addEventListener(r.type, r.listener = a, r.options = e), void (r.value = n);
			this.addEventListener(t.type, a, e),
			r = {
				type: t.type,
				name: t.name,
				value: n,
				listener: a,
				options: e
			},
			i ? i.push(r) : this.__on = [r]
		}
	}
	function Zi(t, n, e) {
		var r = wi(t),
			i = r.CustomEvent;
		"function" == typeof i ? i = new i(n, e) : (i = r.document.createEvent("Event"), e ? (i.initEvent(n, e.bubbles, e.cancelable), i.detail = e.detail) : i.initEvent(n, !1, !1)),
		t.dispatchEvent(i)
	}
	function Qi(t, n) {
		return function() {
			return Zi(this, t, n)
		}
	}
	function Ji(t, n) {
		return function() {
			return Zi(this, t, n.apply(this, arguments))
		}
	}
	li.prototype = {
		constructor: li,
		appendChild: function(t) {
			return this._parent.insertBefore(t, this._next)
		},
		insertBefore: function(t, n) {
			return this._parent.insertBefore(t, n)
		},
		querySelector: function(t) {
			return this._parent.querySelector(t)
		},
		querySelectorAll: function(t) {
			return this._parent.querySelectorAll(t)
		}
	},
	Ni.prototype = {
		add: function(t) {
			this._names.indexOf(t) < 0 && (this._names.push(t), this._node.setAttribute("class", this._names.join(" ")))
		},
		remove: function(t) {
			var n = this._names.indexOf(t);
			n >= 0 && (this._names.splice(n, 1), this._node.setAttribute("class", this._names.join(" ")))
		},
		contains: function(t) {
			return this._names.indexOf(t) >= 0
		}
	};
	var Ki = [null];
	function ta(t, n) {
		this._groups = t,
		this._parents = n
	}
	function na() {
		return new ta([[document.documentElement]], Ki)
	}
	function ea(t) {
		return "string" == typeof t ? new ta([[document.querySelector(t)]], [document.documentElement]) : new ta([[t]], Ki)
	}
	function ra(t, n) {
		if (t = function(t) {
			let n;
			for (; n = t.sourceEvent;)
				t = n;
			return t
		}(t), void 0 === n && (n = t.currentTarget), n) {
			var e = n.ownerSVGElement || n;
			if (e.createSVGPoint) {
				var r = e.createSVGPoint();
				return r.x = t.clientX, r.y = t.clientY, [(r = r.matrixTransform(n.getScreenCTM().inverse())).x, r.y]
			}
			if (n.getBoundingClientRect) {
				var i = n.getBoundingClientRect();
				return [t.clientX - i.left - n.clientLeft, t.clientY - i.top - n.clientTop]
			}
		}
		return [t.pageX, t.pageY]
	}
	ta.prototype = na.prototype = {
		constructor: ta,
		select: function(t) {
			"function" != typeof t && (t = Qr(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o, u = n[i], l = u.length, s = r[i] = new Array(l), c = 0; c < l; ++c)
					(a = u[c]) && (o = t.call(a, a.__data__, c, u)) && ("__data__" in a && (o.__data__ = a.__data__), s[c] = o);
			return new ta(r, this._parents)
		},
		selectAll: function(t) {
			t = "function" == typeof t ? ti(t) : Kr(t);
			for (var n = this._groups, e = n.length, r = [], i = [], a = 0; a < e; ++a)
				for (var o, u = n[a], l = u.length, s = 0; s < l; ++s)
					(o = u[s]) && (r.push(t.call(o, o.__data__, s, u)), i.push(o));
			return new ta(r, i)
		},
		selectChild: function(t) {
			return this.select(null == t ? ii : function(t) {
				return function() {
					return ri.call(this.children, t)
				}
			}("function" == typeof t ? t : ei(t)))
		},
		selectChildren: function(t) {
			return this.selectAll(null == t ? oi : function(t) {
				return function() {
					return ai.call(this.children, t)
				}
			}("function" == typeof t ? t : ei(t)))
		},
		filter: function(t) {
			"function" != typeof t && (t = ni(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o = n[i], u = o.length, l = r[i] = [], s = 0; s < u; ++s)
					(a = o[s]) && t.call(a, a.__data__, s, o) && l.push(a);
			return new ta(r, this._parents)
		},
		data: function(t, n) {
			if (!arguments.length)
				return Array.from(this, fi);
			var e,
				r = n ? ci : si,
				i = this._parents,
				a = this._groups;
			"function" != typeof t && (e = t, t = function() {
				return e
			});
			for (var o = a.length, u = new Array(o), l = new Array(o), s = new Array(o), c = 0; c < o; ++c) {
				var f = i[c],
					h = a[c],
					p = h.length,
					g = hi(t.call(f, f && f.__data__, c, i)),
					d = g.length,
					m = l[c] = new Array(d),
					v = u[c] = new Array(d);
				r(f, h, m, v, s[c] = new Array(p), g, n);
				for (var y, b, w = 0, _ = 0; w < d; ++w)
					if (y = m[w]) {
						for (w >= _ && (_ = w + 1); !(b = v[_]) && ++_ < d;)
							;
						y._next = b || null
					}
			}
			return (u = new ta(u, i))._enter = l, u._exit = s, u
		},
		enter: function() {
			return new ta(this._enter || this._groups.map(ui), this._parents)
		},
		exit: function() {
			return new ta(this._exit || this._groups.map(ui), this._parents)
		},
		join: function(t, n, e) {
			var r = this.enter(),
				i = this,
				a = this.exit();
			return "function" == typeof t ? (r = t(r)) && (r = r.selection()) : r = r.append(t + ""), null != n && (i = n(i)) && (i = i.selection()), null == e ? a.remove() : e(a), r && i ? r.merge(i).order() : i
		},
		merge: function(t) {
			for (var n = t.selection ? t.selection() : t, e = this._groups, r = n._groups, i = e.length, a = r.length, o = Math.min(i, a), u = new Array(i), l = 0; l < o; ++l)
				for (var s, c = e[l], f = r[l], h = c.length, p = u[l] = new Array(h), g = 0; g < h; ++g)
					(s = c[g] || f[g]) && (p[g] = s);
			for (; l < i; ++l)
				u[l] = e[l];
			return new ta(u, this._parents)
		},
		selection: function() {
			return this
		},
		order: function() {
			for (var t = this._groups, n = -1, e = t.length; ++n < e;)
				for (var r, i = t[n], a = i.length - 1, o = i[a]; --a >= 0;)
					(r = i[a]) && (o && 4 ^ r.compareDocumentPosition(o) && o.parentNode.insertBefore(r, o), o = r);
			return this
		},
		sort: function(t) {
			function n(n, e) {
				return n && e ? t(n.__data__, e.__data__) : !n - !e
			}
			t || (t = pi);
			for (var e = this._groups, r = e.length, i = new Array(r), a = 0; a < r; ++a) {
				for (var o, u = e[a], l = u.length, s = i[a] = new Array(l), c = 0; c < l; ++c)
					(o = u[c]) && (s[c] = o);
				s.sort(n)
			}
			return new ta(i, this._parents).order()
		},
		call: function() {
			var t = arguments[0];
			return arguments[0] = this, t.apply(null, arguments), this
		},
		nodes: function() {
			return Array.from(this)
		},
		node: function() {
			for (var t = this._groups, n = 0, e = t.length; n < e; ++n)
				for (var r = t[n], i = 0, a = r.length; i < a; ++i) {
					var o = r[i];
					if (o)
						return o
				}
			return null
		},
		size: function() {
			let t = 0;
			for (const n of this)
				++t;
			return t
		},
		empty: function() {
			return !this.node()
		},
		each: function(t) {
			for (var n = this._groups, e = 0, r = n.length; e < r; ++e)
				for (var i, a = n[e], o = 0, u = a.length; o < u; ++o)
					(i = a[o]) && t.call(i, i.__data__, o, a);
			return this
		},
		attr: function(t, n) {
			var e = Xr(t);
			if (arguments.length < 2) {
				var r = this.node();
				return e.local ? r.getAttributeNS(e.space, e.local) : r.getAttribute(e)
			}
			return this.each((null == n ? e.local ? di : gi : "function" == typeof n ? e.local ? bi : yi : e.local ? vi : mi)(e, n))
		},
		style: function(t, n, e) {
			return arguments.length > 1 ? this.each((null == n ? _i : "function" == typeof n ? Mi : xi)(t, n, null == e ? "" : e)) : Ai(this.node(), t)
		},
		property: function(t, n) {
			return arguments.length > 1 ? this.each((null == n ? Si : "function" == typeof n ? Ci : ki)(t, n)) : this.node()[t]
		},
		classed: function(t, n) {
			var e = Ti(t + "");
			if (arguments.length < 2) {
				for (var r = Di(this.node()), i = -1, a = e.length; ++i < a;)
					if (!r.contains(e[i]))
						return !1;
				return !0
			}
			return this.each(("function" == typeof n ? Li : n ? Fi : Hi)(e, n))
		},
		text: function(t) {
			return arguments.length ? this.each(null == t ? Ui : ("function" == typeof t ? Yi : Ri)(t)) : this.node().textContent
		},
		html: function(t) {
			return arguments.length ? this.each(null == t ? Oi : ("function" == typeof t ? ji : Pi)(t)) : this.node().innerHTML
		},
		raise: function() {
			return this.each($i)
		},
		lower: function() {
			return this.each(Ii)
		},
		append: function(t) {
			var n = "function" == typeof t ? t : Gr(t);
			return this.select((function() {
				return this.appendChild(n.apply(this, arguments))
			}))
		},
		insert: function(t, n) {
			var e = "function" == typeof t ? t : Gr(t),
				r = null == n ? qi : "function" == typeof n ? n : Qr(n);
			return this.select((function() {
				return this.insertBefore(e.apply(this, arguments), r.apply(this, arguments) || null)
			}))
		},
		remove: function() {
			return this.each(Bi)
		},
		clone: function(t) {
			return this.select(t ? Vi : Xi)
		},
		datum: function(t) {
			return arguments.length ? this.property("__data__", t) : this.node().__data__
		},
		on: function(t, n, e) {
			var r,
				i,
				a = function(t) {
					return t.trim().split(/^|\s+/).map((function(t) {
						var n = "",
							e = t.indexOf(".");
						return e >= 0 && (n = t.slice(e + 1), t = t.slice(0, e)), {
							type: t,
							name: n
						}
					}))
				}(t + ""),
				o = a.length;
			if (!(arguments.length < 2)) {
				for (u = n ? Gi : Wi, r = 0; r < o; ++r)
					this.each(u(a[r], n, e));
				return this
			}
			var u = this.node().__on;
			if (u)
				for (var l, s = 0, c = u.length; s < c; ++s)
					for (r = 0, l = u[s]; r < o; ++r)
						if ((i = a[r]).type === l.type && i.name === l.name)
							return l.value
		},
		dispatch: function(t, n) {
			return this.each(("function" == typeof n ? Ji : Qi)(t, n))
		},
		[Symbol.iterator]: function* () {
			for (var t = this._groups, n = 0, e = t.length; n < e; ++n)
				for (var r, i = t[n], a = 0, o = i.length; a < o; ++a)
					(r = i[a]) && (yield r)
		}
	};
	var ia = "$";
	function aa() {}
	function oa(t, n) {
		var e = new aa;
		if (t instanceof aa)
			t.each((function(t, n) {
				e.set(n, t)
			}));
		else if (Array.isArray(t)) {
			var r,
				i = -1,
				a = t.length;
			if (null == n)
				for (; ++i < a;)
					e.set(i, t[i]);
			else
				for (; ++i < a;)
					e.set(n(r = t[i], i, t), r)
		} else if (t)
			for (var o in t)
				e.set(o, t[o]);
		return e
	}
	function ua() {}
	aa.prototype = oa.prototype = {
		constructor: aa,
		has: function(t) {
			return ia + t in this
		},
		get: function(t) {
			return this[ia + t]
		},
		set: function(t, n) {
			return this[ia + t] = n, this
		},
		remove: function(t) {
			var n = ia + t;
			return n in this && delete this[n]
		},
		clear: function() {
			for (var t in this)
				t[0] === ia && delete this[t]
		},
		keys: function() {
			var t = [];
			for (var n in this)
				n[0] === ia && t.push(n.slice(1));
			return t
		},
		values: function() {
			var t = [];
			for (var n in this)
				n[0] === ia && t.push(this[n]);
			return t
		},
		entries: function() {
			var t = [];
			for (var n in this)
				n[0] === ia && t.push({
					key: n.slice(1),
					value: this[n]
				});
			return t
		},
		size: function() {
			var t = 0;
			for (var n in this)
				n[0] === ia && ++t;
			return t
		},
		empty: function() {
			for (var t in this)
				if (t[0] === ia)
					return !1;
			return !0
		},
		each: function(t) {
			for (var n in this)
				n[0] === ia && t(this[n], n.slice(1), this)
		}
	};
	var la = oa.prototype;
	ua.prototype = {
		constructor: ua,
		has: la.has,
		add: function(t) {
			return this[ia + (t += "")] = t, this
		},
		remove: la.remove,
		clear: la.clear,
		values: la.keys,
		size: la.size,
		empty: la.empty,
		each: la.each
	};
	var sa = "http://www.w3.org/1999/xhtml",
		ca = {
			svg: "http://www.w3.org/2000/svg",
			xhtml: sa,
			xlink: "http://www.w3.org/1999/xlink",
			xml: "http://www.w3.org/XML/1998/namespace",
			xmlns: "http://www.w3.org/2000/xmlns/"
		};
	function fa(t) {
		var n = t += "",
			e = n.indexOf(":");
		return e >= 0 && "xmlns" !== (n = t.slice(0, e)) && (t = t.slice(e + 1)), ca.hasOwnProperty(n) ? {
			space: ca[n],
			local: t
		} : t
	}
	function ha(t) {
		return function() {
			var n = this.ownerDocument,
				e = this.namespaceURI;
			return e === sa && n.documentElement.namespaceURI === sa ? n.createElement(t) : n.createElementNS(e, t)
		}
	}
	function pa(t) {
		return function() {
			return this.ownerDocument.createElementNS(t.space, t.local)
		}
	}
	function ga(t) {
		var n = fa(t);
		return (n.local ? pa : ha)(n)
	}
	function da() {}
	function ma(t) {
		return null == t ? da : function() {
			return this.querySelector(t)
		}
	}
	function va() {
		return []
	}
	function ya(t) {
		return new Array(t.length)
	}
	function ba(t, n) {
		this.ownerDocument = t.ownerDocument,
		this.namespaceURI = t.namespaceURI,
		this._next = null,
		this._parent = t,
		this.__data__ = n
	}
	ba.prototype = {
		constructor: ba,
		appendChild: function(t) {
			return this._parent.insertBefore(t, this._next)
		},
		insertBefore: function(t, n) {
			return this._parent.insertBefore(t, n)
		},
		querySelector: function(t) {
			return this._parent.querySelector(t)
		},
		querySelectorAll: function(t) {
			return this._parent.querySelectorAll(t)
		}
	};
	var wa = "$";
	function _a(t, n, e, r, i, a) {
		for (var o, u = 0, l = n.length, s = a.length; u < s; ++u)
			(o = n[u]) ? (o.__data__ = a[u], r[u] = o) : e[u] = new ba(t, a[u]);
		for (; u < l; ++u)
			(o = n[u]) && (i[u] = o)
	}
	function xa(t, n, e, r, i, a, o) {
		var u,
			l,
			s,
			c = {},
			f = n.length,
			h = a.length,
			p = new Array(f);
		for (u = 0; u < f; ++u)
			(l = n[u]) && (p[u] = s = wa + o.call(l, l.__data__, u, n), s in c ? i[u] = l : c[s] = l);
		for (u = 0; u < h; ++u)
			(l = c[s = wa + o.call(t, a[u], u, a)]) ? (r[u] = l, l.__data__ = a[u], c[s] = null) : e[u] = new ba(t, a[u]);
		for (u = 0; u < f; ++u)
			(l = n[u]) && c[p[u]] === l && (i[u] = l)
	}
	function Ma(t, n) {
		return t < n ? -1 : t > n ? 1 : t >= n ? 0 : NaN
	}
	function Aa(t) {
		return function() {
			this.removeAttribute(t)
		}
	}
	function Sa(t) {
		return function() {
			this.removeAttributeNS(t.space, t.local)
		}
	}
	function ka(t, n) {
		return function() {
			this.setAttribute(t, n)
		}
	}
	function Ca(t, n) {
		return function() {
			this.setAttributeNS(t.space, t.local, n)
		}
	}
	function Ta(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttribute(t) : this.setAttribute(t, e)
		}
	}
	function Da(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttributeNS(t.space, t.local) : this.setAttributeNS(t.space, t.local, e)
		}
	}
	function Na(t) {
		return t.ownerDocument && t.ownerDocument.defaultView || t.document && t || t.defaultView
	}
	function za(t) {
		return function() {
			this.style.removeProperty(t)
		}
	}
	function Ea(t, n, e) {
		return function() {
			this.style.setProperty(t, n, e)
		}
	}
	function Fa(t, n, e) {
		return function() {
			var r = n.apply(this, arguments);
			null == r ? this.style.removeProperty(t) : this.style.setProperty(t, r, e)
		}
	}
	function Ha(t) {
		return function() {
			delete this[t]
		}
	}
	function La(t, n) {
		return function() {
			this[t] = n
		}
	}
	function Ua(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? delete this[t] : this[t] = e
		}
	}
	function Ra(t) {
		return t.trim().split(/^|\s+/)
	}
	function Ya(t) {
		return t.classList || new Oa(t)
	}
	function Oa(t) {
		this._node = t,
		this._names = Ra(t.getAttribute("class") || "")
	}
	function Pa(t, n) {
		for (var e = Ya(t), r = -1, i = n.length; ++r < i;)
			e.add(n[r])
	}
	function ja(t, n) {
		for (var e = Ya(t), r = -1, i = n.length; ++r < i;)
			e.remove(n[r])
	}
	function $a(t) {
		return function() {
			Pa(this, t)
		}
	}
	function Ia(t) {
		return function() {
			ja(this, t)
		}
	}
	function qa(t, n) {
		return function() {
			(n.apply(this, arguments) ? Pa : ja)(this, t)
		}
	}
	function Ba() {
		this.textContent = ""
	}
	function Xa(t) {
		return function() {
			this.textContent = t
		}
	}
	function Va(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.textContent = null == n ? "" : n
		}
	}
	function Wa() {
		this.innerHTML = ""
	}
	function Ga(t) {
		return function() {
			this.innerHTML = t
		}
	}
	function Za(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.innerHTML = null == n ? "" : n
		}
	}
	function Qa() {
		this.nextSibling && this.parentNode.appendChild(this)
	}
	function Ja() {
		this.previousSibling && this.parentNode.insertBefore(this, this.parentNode.firstChild)
	}
	function Ka() {
		return null
	}
	function to() {
		var t = this.parentNode;
		t && t.removeChild(this)
	}
	function no() {
		var t = this.cloneNode(!1),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	function eo() {
		var t = this.cloneNode(!0),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	Oa.prototype = {
		add: function(t) {
			this._names.indexOf(t) < 0 && (this._names.push(t), this._node.setAttribute("class", this._names.join(" ")))
		},
		remove: function(t) {
			var n = this._names.indexOf(t);
			n >= 0 && (this._names.splice(n, 1), this._node.setAttribute("class", this._names.join(" ")))
		},
		contains: function(t) {
			return this._names.indexOf(t) >= 0
		}
	};
	var ro = {};
	"undefined" != typeof document && ("onmouseenter" in document.documentElement || (ro = {
		mouseenter: "mouseover",
		mouseleave: "mouseout"
	}));
	function io(t, n, e) {
		return t = ao(t, n, e), function(n) {
			var e = n.relatedTarget;
			e && (e === this || 8 & e.compareDocumentPosition(this)) || t.call(this, n)
		}
	}
	function ao(t, n, e) {
		return function(r) {
			try {
				t.call(this, this.__data__, n, e)
			} finally {}
		}
	}
	function oo(t) {
		return function() {
			var n = this.__on;
			if (n) {
				for (var e, r = 0, i = -1, a = n.length; r < a; ++r)
					e = n[r],
					t.type && e.type !== t.type || e.name !== t.name ? n[++i] = e : this.removeEventListener(e.type, e.listener, e.capture);
				++i ? n.length = i : delete this.__on
			}
		}
	}
	function uo(t, n, e) {
		var r = ro.hasOwnProperty(t.type) ? io : ao;
		return function(i, a, o) {
			var u,
				l = this.__on,
				s = r(n, a, o);
			if (l)
				for (var c = 0, f = l.length; c < f; ++c)
					if ((u = l[c]).type === t.type && u.name === t.name)
						return this.removeEventListener(u.type, u.listener, u.capture), this.addEventListener(u.type, u.listener = s, u.capture = e), void (u.value = n);
			this.addEventListener(t.type, s, e),
			u = {
				type: t.type,
				name: t.name,
				value: n,
				listener: s,
				capture: e
			},
			l ? l.push(u) : this.__on = [u]
		}
	}
	function lo(t, n, e) {
		var r = Na(t),
			i = r.CustomEvent;
		"function" == typeof i ? i = new i(n, e) : (i = r.document.createEvent("Event"), e ? (i.initEvent(n, e.bubbles, e.cancelable), i.detail = e.detail) : i.initEvent(n, !1, !1)),
		t.dispatchEvent(i)
	}
	function so(t, n) {
		return function() {
			return lo(this, t, n)
		}
	}
	function co(t, n) {
		return function() {
			return lo(this, t, n.apply(this, arguments))
		}
	}
	var fo = [null];
	function ho(t, n) {
		this._groups = t,
		this._parents = n
	}
	function po() {
		return new ho([[document.documentElement]], fo)
	}
	function go(t) {
		return "string" == typeof t ? new ho([[document.querySelector(t)]], [document.documentElement]) : new ho([[t]], fo)
	}
	function mo() {
		var t = function() {
				return "n"
			},
			n = function() {
				return [0, 0]
			},
			e = function() {
				return " "
			},
			r = document.body,
			i = f(),
			a = null,
			o = null,
			u = null;
		function l(t) {
			a = function(t) {
				var n = t.node();
				return n ? "svg" === n.tagName.toLowerCase() ? n : n.ownerSVGElement : null
			}(t),
			a && (o = a.createSVGPoint(), r.appendChild(i))
		}
		l.show = function() {
			var i = Array.prototype.slice.call(arguments);
			i[i.length - 1] instanceof SVGElement && (u = i.pop());
			var a,
				o = e.apply(this, i),
				f = n.apply(this, i),
				p = t.apply(this, i),
				g = h(),
				d = c.length,
				m = document.documentElement.scrollTop || r.scrollTop,
				v = document.documentElement.scrollLeft || r.scrollLeft;
			for (g.html(o).style("opacity", 1).style("pointer-events", "all"); d--;)
				g.classed(c[d], !1);
			return a = s.get(p).apply(this), g.classed(p, !0).style("top", a.top + f[0] + m + "px").style("left", a.left + f[1] + v + "px"), l
		},
		l.hide = function() {
			return h().style("opacity", 0).style("pointer-events", "none"), l
		},
		l.attr = function(t, n) {
			if (arguments.length < 2 && "string" == typeof t)
				return h().attr(t);
			var e = Array.prototype.slice.call(arguments);
			return po.prototype.attr.apply(h(), e), l
		},
		l.style = function(t, n) {
			if (arguments.length < 2 && "string" == typeof t)
				return h().style(t);
			var e = Array.prototype.slice.call(arguments);
			return po.prototype.style.apply(h(), e), l
		},
		l.direction = function(n) {
			return arguments.length ? (t = null == n ? n : g(n), l) : t
		},
		l.offset = function(t) {
			return arguments.length ? (n = null == t ? t : g(t), l) : n
		},
		l.html = function(t) {
			return arguments.length ? (e = null == t ? t : g(t), l) : e
		},
		l.rootElement = function(t) {
			return arguments.length ? (r = null == t ? t : g(t), l) : r
		},
		l.destroy = function() {
			return i && (h().remove(), i = null), l
		};
		var s = oa({
				n: function() {
					var t = p(this);
					return {
						top: t.n.y - i.offsetHeight,
						left: t.n.x - i.offsetWidth / 2
					}
				},
				s: function() {
					var t = p(this);
					return {
						top: t.s.y,
						left: t.s.x - i.offsetWidth / 2
					}
				},
				e: function() {
					var t = p(this);
					return {
						top: t.e.y - i.offsetHeight / 2,
						left: t.e.x
					}
				},
				w: function() {
					var t = p(this);
					return {
						top: t.w.y - i.offsetHeight / 2,
						left: t.w.x - i.offsetWidth
					}
				},
				nw: function() {
					var t = p(this);
					return {
						top: t.nw.y - i.offsetHeight,
						left: t.nw.x - i.offsetWidth
					}
				},
				ne: function() {
					var t = p(this);
					return {
						top: t.ne.y - i.offsetHeight,
						left: t.ne.x
					}
				},
				sw: function() {
					var t = p(this);
					return {
						top: t.sw.y,
						left: t.sw.x - i.offsetWidth
					}
				},
				se: function() {
					var t = p(this);
					return {
						top: t.se.y,
						left: t.se.x
					}
				}
			}),
			c = s.keys();
		function f() {
			var t = go(document.createElement("div"));
			return t.style("position", "absolute").style("top", 0).style("opacity", 0).style("pointer-events", "none").style("box-sizing", "border-box"), t.node()
		}
		function h() {
			return null == i && (i = f(), r.appendChild(i)), go(i)
		}
		function p(t) {
			for (var n = u || t; null == n.getScreenCTM && null != n.parentNode;)
				n = n.parentNode;
			var e = {},
				r = n.getScreenCTM(),
				i = n.getBBox(),
				a = i.width,
				l = i.height,
				s = i.x,
				c = i.y;
			return o.x = s, o.y = c, e.nw = o.matrixTransform(r), o.x += a, e.ne = o.matrixTransform(r), o.y += l, e.se = o.matrixTransform(r), o.x -= a, e.sw = o.matrixTransform(r), o.y -= l / 2, e.w = o.matrixTransform(r), o.x += a, e.e = o.matrixTransform(r), o.x -= a / 2, o.y -= l / 2, e.n = o.matrixTransform(r), o.y += l, e.s = o.matrixTransform(r), e
		}
		function g(t) {
			return "function" == typeof t ? t : function() {
				return t
			}
		}
		return l
	}
	function vo(t) {
		for (var n = t.length / 6 | 0, e = new Array(n), r = 0; r < n;)
			e[r] = "#" + t.slice(6 * r, 6 * ++r);
		return e
	}
	ho.prototype = po.prototype = {
		constructor: ho,
		select: function(t) {
			"function" != typeof t && (t = ma(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o, u = n[i], l = u.length, s = r[i] = new Array(l), c = 0; c < l; ++c)
					(a = u[c]) && (o = t.call(a, a.__data__, c, u)) && ("__data__" in a && (o.__data__ = a.__data__), s[c] = o);
			return new ho(r, this._parents)
		},
		selectAll: function(t) {
			"function" != typeof t && (t = function(t) {
				return null == t ? va : function() {
					return this.querySelectorAll(t)
				}
			}(t));
			for (var n = this._groups, e = n.length, r = [], i = [], a = 0; a < e; ++a)
				for (var o, u = n[a], l = u.length, s = 0; s < l; ++s)
					(o = u[s]) && (r.push(t.call(o, o.__data__, s, u)), i.push(o));
			return new ho(r, i)
		},
		filter: function(t) {
			"function" != typeof t && (t = function(t) {
				return function() {
					return this.matches(t)
				}
			}(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o = n[i], u = o.length, l = r[i] = [], s = 0; s < u; ++s)
					(a = o[s]) && t.call(a, a.__data__, s, o) && l.push(a);
			return new ho(r, this._parents)
		},
		data: function(t, n) {
			if (!t)
				return g = new Array(this.size()), c = -1, this.each((function(t) {
					g[++c] = t
				})), g;
			var e,
				r = n ? xa : _a,
				i = this._parents,
				a = this._groups;
			"function" != typeof t && (e = t, t = function() {
				return e
			});
			for (var o = a.length, u = new Array(o), l = new Array(o), s = new Array(o), c = 0; c < o; ++c) {
				var f = i[c],
					h = a[c],
					p = h.length,
					g = t.call(f, f && f.__data__, c, i),
					d = g.length,
					m = l[c] = new Array(d),
					v = u[c] = new Array(d);
				r(f, h, m, v, s[c] = new Array(p), g, n);
				for (var y, b, w = 0, _ = 0; w < d; ++w)
					if (y = m[w]) {
						for (w >= _ && (_ = w + 1); !(b = v[_]) && ++_ < d;)
							;
						y._next = b || null
					}
			}
			return (u = new ho(u, i))._enter = l, u._exit = s, u
		},
		enter: function() {
			return new ho(this._enter || this._groups.map(ya), this._parents)
		},
		exit: function() {
			return new ho(this._exit || this._groups.map(ya), this._parents)
		},
		join: function(t, n, e) {
			var r = this.enter(),
				i = this,
				a = this.exit();
			return r = "function" == typeof t ? t(r) : r.append(t + ""), null != n && (i = n(i)), null == e ? a.remove() : e(a), r && i ? r.merge(i).order() : i
		},
		merge: function(t) {
			for (var n = this._groups, e = t._groups, r = n.length, i = e.length, a = Math.min(r, i), o = new Array(r), u = 0; u < a; ++u)
				for (var l, s = n[u], c = e[u], f = s.length, h = o[u] = new Array(f), p = 0; p < f; ++p)
					(l = s[p] || c[p]) && (h[p] = l);
			for (; u < r; ++u)
				o[u] = n[u];
			return new ho(o, this._parents)
		},
		order: function() {
			for (var t = this._groups, n = -1, e = t.length; ++n < e;)
				for (var r, i = t[n], a = i.length - 1, o = i[a]; --a >= 0;)
					(r = i[a]) && (o && 4 ^ r.compareDocumentPosition(o) && o.parentNode.insertBefore(r, o), o = r);
			return this
		},
		sort: function(t) {
			function n(n, e) {
				return n && e ? t(n.__data__, e.__data__) : !n - !e
			}
			t || (t = Ma);
			for (var e = this._groups, r = e.length, i = new Array(r), a = 0; a < r; ++a) {
				for (var o, u = e[a], l = u.length, s = i[a] = new Array(l), c = 0; c < l; ++c)
					(o = u[c]) && (s[c] = o);
				s.sort(n)
			}
			return new ho(i, this._parents).order()
		},
		call: function() {
			var t = arguments[0];
			return arguments[0] = this, t.apply(null, arguments), this
		},
		nodes: function() {
			var t = new Array(this.size()),
				n = -1;
			return this.each((function() {
				t[++n] = this
			})), t
		},
		node: function() {
			for (var t = this._groups, n = 0, e = t.length; n < e; ++n)
				for (var r = t[n], i = 0, a = r.length; i < a; ++i) {
					var o = r[i];
					if (o)
						return o
				}
			return null
		},
		size: function() {
			var t = 0;
			return this.each((function() {
				++t
			})), t
		},
		empty: function() {
			return !this.node()
		},
		each: function(t) {
			for (var n = this._groups, e = 0, r = n.length; e < r; ++e)
				for (var i, a = n[e], o = 0, u = a.length; o < u; ++o)
					(i = a[o]) && t.call(i, i.__data__, o, a);
			return this
		},
		attr: function(t, n) {
			var e = fa(t);
			if (arguments.length < 2) {
				var r = this.node();
				return e.local ? r.getAttributeNS(e.space, e.local) : r.getAttribute(e)
			}
			return this.each((null == n ? e.local ? Sa : Aa : "function" == typeof n ? e.local ? Da : Ta : e.local ? Ca : ka)(e, n))
		},
		style: function(t, n, e) {
			return arguments.length > 1 ? this.each((null == n ? za : "function" == typeof n ? Fa : Ea)(t, n, null == e ? "" : e)) : function(t, n) {
				return t.style.getPropertyValue(n) || Na(t).getComputedStyle(t, null).getPropertyValue(n)
			}(this.node(), t)
		},
		property: function(t, n) {
			return arguments.length > 1 ? this.each((null == n ? Ha : "function" == typeof n ? Ua : La)(t, n)) : this.node()[t]
		},
		classed: function(t, n) {
			var e = Ra(t + "");
			if (arguments.length < 2) {
				for (var r = Ya(this.node()), i = -1, a = e.length; ++i < a;)
					if (!r.contains(e[i]))
						return !1;
				return !0
			}
			return this.each(("function" == typeof n ? qa : n ? $a : Ia)(e, n))
		},
		text: function(t) {
			return arguments.length ? this.each(null == t ? Ba : ("function" == typeof t ? Va : Xa)(t)) : this.node().textContent
		},
		html: function(t) {
			return arguments.length ? this.each(null == t ? Wa : ("function" == typeof t ? Za : Ga)(t)) : this.node().innerHTML
		},
		raise: function() {
			return this.each(Qa)
		},
		lower: function() {
			return this.each(Ja)
		},
		append: function(t) {
			var n = "function" == typeof t ? t : ga(t);
			return this.select((function() {
				return this.appendChild(n.apply(this, arguments))
			}))
		},
		insert: function(t, n) {
			var e = "function" == typeof t ? t : ga(t),
				r = null == n ? Ka : "function" == typeof n ? n : ma(n);
			return this.select((function() {
				return this.insertBefore(e.apply(this, arguments), r.apply(this, arguments) || null)
			}))
		},
		remove: function() {
			return this.each(to)
		},
		clone: function(t) {
			return this.select(t ? eo : no)
		},
		datum: function(t) {
			return arguments.length ? this.property("__data__", t) : this.node().__data__
		},
		on: function(t, n, e) {
			var r,
				i,
				a = function(t) {
					return t.trim().split(/^|\s+/).map((function(t) {
						var n = "",
							e = t.indexOf(".");
						return e >= 0 && (n = t.slice(e + 1), t = t.slice(0, e)), {
							type: t,
							name: n
						}
					}))
				}(t + ""),
				o = a.length;
			if (!(arguments.length < 2)) {
				for (u = n ? uo : oo, null == e && (e = !1), r = 0; r < o; ++r)
					this.each(u(a[r], n, e));
				return this
			}
			var u = this.node().__on;
			if (u)
				for (var l, s = 0, c = u.length; s < c; ++s)
					for (r = 0, l = u[s]; r < o; ++r)
						if ((i = a[r]).type === l.type && i.name === l.name)
							return l.value
		},
		dispatch: function(t, n) {
			return this.each(("function" == typeof n ? co : so)(t, n))
		}
	};
	var yo = vo("1f77b4ff7f0e2ca02cd627289467bd8c564be377c27f7f7fbcbd2217becf"),
		bo = vo("8dd3c7ffffb3bebadafb807280b1d3fdb462b3de69fccde5d9d9d9bc80bdccebc5ffed6f"),
		wo = (t => Ft(t[t.length - 1]))(new Array(3).concat("fc8d59ffffbf91bfdb", "d7191cfdae61abd9e92c7bb6", "d7191cfdae61ffffbfabd9e92c7bb6", "d73027fc8d59fee090e0f3f891bfdb4575b4", "d73027fc8d59fee090ffffbfe0f3f891bfdb4575b4", "d73027f46d43fdae61fee090e0f3f8abd9e974add14575b4", "d73027f46d43fdae61fee090ffffbfe0f3f8abd9e974add14575b4", "a50026d73027f46d43fdae61fee090e0f3f8abd9e974add14575b4313695", "a50026d73027f46d43fdae61fee090ffffbfe0f3f8abd9e974add14575b4313695").map(vo)),
		_o = s({
			init: function(t) {
				t.parentNode.appendChild(t)
			}
		}),
		xo = s({
			props: {
				id: {},
				colorScale: {
					default: An().range(["black", "white"])
				},
				angle: {
					default: 0
				}
			},
			init: function(t, n) {
				n.id = "areaGradient".concat(Math.round(1e4 * Math.random())),
				n.gradient = ea(t).append("linearGradient")
			},
			update: function(t) {
				var n = Math.PI * t.angle / 180;
				t.gradient.attr("y1", Math.round(100 * Math.max(0, Math.sin(n))) + "%").attr("y2", Math.round(100 * Math.max(0, -Math.sin(n))) + "%").attr("x1", Math.round(100 * Math.max(0, -Math.cos(n))) + "%").attr("x2", Math.round(100 * Math.max(0, Math.cos(n))) + "%").attr("id", t.id);
				var e = An().domain([0, 100]).range(t.colorScale.domain()),
					r = t.gradient.selectAll("stop").data(C(0, 100.01, 20));
				r.exit().remove(),
				r.merge(r.enter().append("stop")).attr("offset", (function(t) {
					return "".concat(t, "%")
				})).attr("stop-color", (function(n) {
					return t.colorScale(e(n))
				}))
			}
		});
	function Mo(t) {
		return function(t) {
				if (Array.isArray(t))
					return Ao(t)
			}(t) || function(t) {
				if ("undefined" != typeof Symbol && null != t[Symbol.iterator] || null != t["@@iterator"])
					return Array.from(t)
			}(t) || function(t, n) {
				if (!t)
					return;
				if ("string" == typeof t)
					return Ao(t, n);
				var e = Object.prototype.toString.call(t).slice(8, -1);
				"Object" === e && t.constructor && (e = t.constructor.name);
				if ("Map" === e || "Set" === e)
					return Array.from(t);
				if ("Arguments" === e || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(e))
					return Ao(t, n)
			}(t) || function() {
				throw new TypeError("Invalid attempt to spread non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")
			}()
	}
	function Ao(t, n) {
		(null == n || n > t.length) && (n = t.length);
		for (var e = 0, r = new Array(n); e < n; e++)
			r[e] = t[e];
		return r
	}
	s({
		props: {
			id: {
				default: "areaGradient".concat(Math.round(1e4 * Math.random()))
			}
		},
		init: function(t, n) {
			n.filter = ea(t).append("defs").append("filter").attr("height", "130%"),
			n.filter.append("feGaussianBlur").attr("in", "SourceAlpha").attr("stdDeviation", 3),
			n.filter.append("feOffset").attr("dx", 2).attr("dy", 2).attr("result", "offsetblur");
			var e = n.filter.append("feMerge");
			e.append("feMergeNode"),
			e.append("feMergeNode").attr("in", "SourceGraphic")
		},
		update: function(t) {
			t.filter.attr("id", t.id)
		}
	}),
	s({
		props: {
			x: {
				default: 0
			},
			y: {
				default: 0
			},
			r: {
				default: 8
			},
			color: {
				default: "darkblue"
			},
			duration: {
				default: .7
			},
			angleFull: {
				default: 120
			}
		},
		init: function(t, n) {
			t = ea(t),
			n.path = t.append("path"),
			n.transform = n.path.append("animateTransform").attr("attributeName", "transform").attr("attributeType", "XML").attr("type", "rotate").attr("begin", "0s").attr("fill", "freeze").attr("repeatCount", "indefinite")
		},
		update: function(t) {
			t.path.attr("d", function(t, n, e, r, i, a) {
				i = i / 180 * Math.PI,
				a = a / 180 * Math.PI;
				var o = e,
					u = e - r,
					l = [[t + o * Math.cos(i), n + o * Math.sin(i)], [t + o * Math.cos(a), n + o * Math.sin(a)], [t + u * Math.cos(a), n + u * Math.sin(a)], [t + u * Math.cos(i), n + u * Math.sin(i)]],
					s = (a - i) % (2 * Math.PI) > Math.PI ? 1 : 0,
					c = [];
				return c.push("M" + l[0].join()), c.push("A" + [o, o, 0, s, 1, l[1]].join()), c.push("L" + l[2].join()), c.push("A" + [u, u, 0, s, 0, l[3]].join()), c.push("z"), c.join(" ")
			}(t.x, t.y, t.r, t.r / 3, 0, t.angleFull)).attr("fill", t.color),
			t.transform.attr("from", "0 " + t.x + " " + t.y).attr("to", "360 " + t.x + " " + t.y).attr("dur", t.duration + "s")
		}
	}),
	s({
		props: {
			imgUrl: {},
			x: {
				default: 0
			},
			y: {
				default: 0
			},
			maxWidth: {
				default: 20
			},
			maxHeight: {
				default: 20
			},
			svgAlign: {
				default: "xMidYMid"
			}
		},
		methods: {
			show: function(t) {
				return t.img.attr("width", t.maxWidth).attr("height", t.maxHeight), this
			},
			hide: function(t) {
				return t.img.attr("width", 0).attr("height", 0), this
			}
		},
		init: function(t, n) {
			n.img = ea(t).append("image")
		},
		update: function(t) {
			t.img.attr("xlink:href", t.imgUrl).attr("x", t.x).attr("y", t.y).attr("width", t.maxW).attr("height", t.maxH).attr("preserveAspectRatio", t.svgAlign + " meet")
		}
	}),
	s({
		props: {
			selection: {
				default: {
					x: [null, null],
					y: [null, null]
				}
			},
			xDomain: {
				onChange: function(t, n) {
					n.xScale.domain(t)
				}
			},
			yDomain: {
				onChange: function(t, n) {
					n.yScale.domain(t)
				}
			},
			transitionDuration: 700
		},
		stateInit: {
			xScale: An(),
			yScale: An()
		},
		init: function(t, n, e) {
			var r = e.width,
				i = e.height,
				a = e.margin,
				o = void 0 === a ? {
					top: 2,
					right: 2,
					bottom: 2,
					left: 2
				} : a;
			n.xScale.range([o.left, r - n.margin.right]),
			n.yScale.range([o.top, i - n.margin.bottom]),
			n.svg = ea(t).append("svg").attr("width", r).attr("height", i),
			n.outerBox = n.svg.append("rect").attr("x", n.xScale.range()[0]).attr("y", n.yScale.range()[0]).attr("rx", 2).attr("ry", 2).attr("width", n.xScale.range()[1]).attr("height", n.yScale.range()[1]).style("fill", "#EEE").style("stroke", "grey"),
			n.selectionBox = n.svg.append("rect").attr("rx", 1).attr("ry", 1).attr("width", 0).attr("height", 0).style("stroke", "blue").style("stroke-opacity", .6).style("fill", "blue").style("fill-opacity", .3)
		},
		update: function(t) {
			t.outerBox.attr("x", t.xScale.range()[0]).attr("y", t.yScale.range()[0]).attr("width", t.xScale.range()[1]).attr("height", t.yScale.range()[1]),
			t.selectionBox.attr("x", t.xScale(t.selection.x[0])).attr("y", t.yScale(t.selection.y[0])).attr("width", t.xScale(t.selection.x[1] - t.selection.x[0])).attr("height", t.yScale(t.selection.y[1] - t.selection.y[0]))
		}
	});
	var So = s({
		props: {
			bbox: {
				default: {
					width: null,
					height: null
				}
			},
			passes: {
				default: 3
			}
		},
		init: function(t, n) {
			n.el = t
		},
		update: function(t) {
			Mo(Array(t.passes).keys()).some((function() {
				var n = parseInt(t.el.style["font-size"].split("px")[0]) || 20,
					e = t.el.getBBox(),
					r = Math.floor(n * Math.min(t.bbox.width / e.width, t.bbox.height / e.height));
				if (r === n)
					return !0;
				t.el.style["font-size"] = r + "px"
			}))
		}
	});
	s({
		props: {
			maxWidth: {
				default: 1 / 0
			}
		},
		init: function(t, n) {
			n.el = t
		},
		update: function(t) {
			for (var n, e, r = t.el.textContent, i = Math.round(r.length * t.maxWidth / t.el.getBBox().width * 1.2); --i && t.maxWidth / t.el.getBBox().width < 1;)
				t.el.textContent = (e = i, (n = r).length <= e ? n : n.substring(0, 2 * e / 3) + "..." + n.substring(n.length - e / 3, n.length))
		}
	});
	var ko = "http://www.w3.org/1999/xhtml",
		Co = {
			svg: "http://www.w3.org/2000/svg",
			xhtml: ko,
			xlink: "http://www.w3.org/1999/xlink",
			xml: "http://www.w3.org/XML/1998/namespace",
			xmlns: "http://www.w3.org/2000/xmlns/"
		};
	function To(t) {
		var n = t += "",
			e = n.indexOf(":");
		return e >= 0 && "xmlns" !== (n = t.slice(0, e)) && (t = t.slice(e + 1)), Co.hasOwnProperty(n) ? {
			space: Co[n],
			local: t
		} : t
	}
	function Do(t) {
		return function() {
			var n = this.ownerDocument,
				e = this.namespaceURI;
			return e === ko && n.documentElement.namespaceURI === ko ? n.createElement(t) : n.createElementNS(e, t)
		}
	}
	function No(t) {
		return function() {
			return this.ownerDocument.createElementNS(t.space, t.local)
		}
	}
	function zo(t) {
		var n = To(t);
		return (n.local ? No : Do)(n)
	}
	function Eo() {}
	function Fo(t) {
		return null == t ? Eo : function() {
			return this.querySelector(t)
		}
	}
	function Ho(t) {
		return "object" == typeof t && "length" in t ? t : Array.from(t)
	}
	function Lo() {
		return []
	}
	function Uo(t) {
		return function(n) {
			return n.matches(t)
		}
	}
	var Ro = Array.prototype.find;
	function Yo() {
		return this.firstElementChild
	}
	var Oo = Array.prototype.filter;
	function Po() {
		return this.children
	}
	function jo(t) {
		return new Array(t.length)
	}
	function $o(t, n) {
		this.ownerDocument = t.ownerDocument,
		this.namespaceURI = t.namespaceURI,
		this._next = null,
		this._parent = t,
		this.__data__ = n
	}
	function Io(t, n, e, r, i, a) {
		for (var o, u = 0, l = n.length, s = a.length; u < s; ++u)
			(o = n[u]) ? (o.__data__ = a[u], r[u] = o) : e[u] = new $o(t, a[u]);
		for (; u < l; ++u)
			(o = n[u]) && (i[u] = o)
	}
	function qo(t, n, e, r, i, a, o) {
		var u,
			l,
			s,
			c = new Map,
			f = n.length,
			h = a.length,
			p = new Array(f);
		for (u = 0; u < f; ++u)
			(l = n[u]) && (p[u] = s = o.call(l, l.__data__, u, n) + "", c.has(s) ? i[u] = l : c.set(s, l));
		for (u = 0; u < h; ++u)
			s = o.call(t, a[u], u, a) + "",
			(l = c.get(s)) ? (r[u] = l, l.__data__ = a[u], c.delete(s)) : e[u] = new $o(t, a[u]);
		for (u = 0; u < f; ++u)
			(l = n[u]) && c.get(p[u]) === l && (i[u] = l)
	}
	function Bo(t) {
		return t.__data__
	}
	function Xo(t, n) {
		return t < n ? -1 : t > n ? 1 : t >= n ? 0 : NaN
	}
	function Vo(t) {
		return function() {
			this.removeAttribute(t)
		}
	}
	function Wo(t) {
		return function() {
			this.removeAttributeNS(t.space, t.local)
		}
	}
	function Go(t, n) {
		return function() {
			this.setAttribute(t, n)
		}
	}
	function Zo(t, n) {
		return function() {
			this.setAttributeNS(t.space, t.local, n)
		}
	}
	function Qo(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttribute(t) : this.setAttribute(t, e)
		}
	}
	function Jo(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? this.removeAttributeNS(t.space, t.local) : this.setAttributeNS(t.space, t.local, e)
		}
	}
	function Ko(t) {
		return t.ownerDocument && t.ownerDocument.defaultView || t.document && t || t.defaultView
	}
	function tu(t) {
		return function() {
			this.style.removeProperty(t)
		}
	}
	function nu(t, n, e) {
		return function() {
			this.style.setProperty(t, n, e)
		}
	}
	function eu(t, n, e) {
		return function() {
			var r = n.apply(this, arguments);
			null == r ? this.style.removeProperty(t) : this.style.setProperty(t, r, e)
		}
	}
	function ru(t) {
		return function() {
			delete this[t]
		}
	}
	function iu(t, n) {
		return function() {
			this[t] = n
		}
	}
	function au(t, n) {
		return function() {
			var e = n.apply(this, arguments);
			null == e ? delete this[t] : this[t] = e
		}
	}
	function ou(t) {
		return t.trim().split(/^|\s+/)
	}
	function uu(t) {
		return t.classList || new lu(t)
	}
	function lu(t) {
		this._node = t,
		this._names = ou(t.getAttribute("class") || "")
	}
	function su(t, n) {
		for (var e = uu(t), r = -1, i = n.length; ++r < i;)
			e.add(n[r])
	}
	function cu(t, n) {
		for (var e = uu(t), r = -1, i = n.length; ++r < i;)
			e.remove(n[r])
	}
	function fu(t) {
		return function() {
			su(this, t)
		}
	}
	function hu(t) {
		return function() {
			cu(this, t)
		}
	}
	function pu(t, n) {
		return function() {
			(n.apply(this, arguments) ? su : cu)(this, t)
		}
	}
	function gu() {
		this.textContent = ""
	}
	function du(t) {
		return function() {
			this.textContent = t
		}
	}
	function mu(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.textContent = null == n ? "" : n
		}
	}
	function vu() {
		this.innerHTML = ""
	}
	function yu(t) {
		return function() {
			this.innerHTML = t
		}
	}
	function bu(t) {
		return function() {
			var n = t.apply(this, arguments);
			this.innerHTML = null == n ? "" : n
		}
	}
	function wu() {
		this.nextSibling && this.parentNode.appendChild(this)
	}
	function _u() {
		this.previousSibling && this.parentNode.insertBefore(this, this.parentNode.firstChild)
	}
	function xu() {
		return null
	}
	function Mu() {
		var t = this.parentNode;
		t && t.removeChild(this)
	}
	function Au() {
		var t = this.cloneNode(!1),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	function Su() {
		var t = this.cloneNode(!0),
			n = this.parentNode;
		return n ? n.insertBefore(t, this.nextSibling) : t
	}
	function ku(t) {
		return function() {
			var n = this.__on;
			if (n) {
				for (var e, r = 0, i = -1, a = n.length; r < a; ++r)
					e = n[r],
					t.type && e.type !== t.type || e.name !== t.name ? n[++i] = e : this.removeEventListener(e.type, e.listener, e.options);
				++i ? n.length = i : delete this.__on
			}
		}
	}
	function Cu(t, n, e) {
		return function() {
			var r,
				i = this.__on,
				a = function(t) {
					return function(n) {
						t.call(this, n, this.__data__)
					}
				}(n);
			if (i)
				for (var o = 0, u = i.length; o < u; ++o)
					if ((r = i[o]).type === t.type && r.name === t.name)
						return this.removeEventListener(r.type, r.listener, r.options), this.addEventListener(r.type, r.listener = a, r.options = e), void (r.value = n);
			this.addEventListener(t.type, a, e),
			r = {
				type: t.type,
				name: t.name,
				value: n,
				listener: a,
				options: e
			},
			i ? i.push(r) : this.__on = [r]
		}
	}
	function Tu(t, n, e) {
		var r = Ko(t),
			i = r.CustomEvent;
		"function" == typeof i ? i = new i(n, e) : (i = r.document.createEvent("Event"), e ? (i.initEvent(n, e.bubbles, e.cancelable), i.detail = e.detail) : i.initEvent(n, !1, !1)),
		t.dispatchEvent(i)
	}
	function Du(t, n) {
		return function() {
			return Tu(this, t, n)
		}
	}
	function Nu(t, n) {
		return function() {
			return Tu(this, t, n.apply(this, arguments))
		}
	}
	$o.prototype = {
		constructor: $o,
		appendChild: function(t) {
			return this._parent.insertBefore(t, this._next)
		},
		insertBefore: function(t, n) {
			return this._parent.insertBefore(t, n)
		},
		querySelector: function(t) {
			return this._parent.querySelector(t)
		},
		querySelectorAll: function(t) {
			return this._parent.querySelectorAll(t)
		}
	},
	lu.prototype = {
		add: function(t) {
			this._names.indexOf(t) < 0 && (this._names.push(t), this._node.setAttribute("class", this._names.join(" ")))
		},
		remove: function(t) {
			var n = this._names.indexOf(t);
			n >= 0 && (this._names.splice(n, 1), this._node.setAttribute("class", this._names.join(" ")))
		},
		contains: function(t) {
			return this._names.indexOf(t) >= 0
		}
	};
	var zu = [null];
	function Eu(t, n) {
		this._groups = t,
		this._parents = n
	}
	function Fu(t) {
		return "string" == typeof t ? new Eu([[document.querySelector(t)]], [document.documentElement]) : new Eu([[t]], zu)
	}
	function Hu(t) {
		return Hu = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(t) {
			return typeof t
		} : function(t) {
			return t && "function" == typeof Symbol && t.constructor === Symbol && t !== Symbol.prototype ? "symbol" : typeof t
		}, Hu(t)
	}
	Eu.prototype = {
		constructor: Eu,
		select: function(t) {
			"function" != typeof t && (t = Fo(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o, u = n[i], l = u.length, s = r[i] = new Array(l), c = 0; c < l; ++c)
					(a = u[c]) && (o = t.call(a, a.__data__, c, u)) && ("__data__" in a && (o.__data__ = a.__data__), s[c] = o);
			return new Eu(r, this._parents)
		},
		selectAll: function(t) {
			t = "function" == typeof t ? function(t) {
				return function() {
					var n = t.apply(this, arguments);
					return null == n ? [] : Ho(n)
				}
			}(t) : function(t) {
				return null == t ? Lo : function() {
					return this.querySelectorAll(t)
				}
			}(t);
			for (var n = this._groups, e = n.length, r = [], i = [], a = 0; a < e; ++a)
				for (var o, u = n[a], l = u.length, s = 0; s < l; ++s)
					(o = u[s]) && (r.push(t.call(o, o.__data__, s, u)), i.push(o));
			return new Eu(r, i)
		},
		selectChild: function(t) {
			return this.select(null == t ? Yo : function(t) {
				return function() {
					return Ro.call(this.children, t)
				}
			}("function" == typeof t ? t : Uo(t)))
		},
		selectChildren: function(t) {
			return this.selectAll(null == t ? Po : function(t) {
				return function() {
					return Oo.call(this.children, t)
				}
			}("function" == typeof t ? t : Uo(t)))
		},
		filter: function(t) {
			"function" != typeof t && (t = function(t) {
				return function() {
					return this.matches(t)
				}
			}(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o = n[i], u = o.length, l = r[i] = [], s = 0; s < u; ++s)
					(a = o[s]) && t.call(a, a.__data__, s, o) && l.push(a);
			return new Eu(r, this._parents)
		},
		data: function(t, n) {
			if (!arguments.length)
				return Array.from(this, Bo);
			var e,
				r = n ? qo : Io,
				i = this._parents,
				a = this._groups;
			"function" != typeof t && (e = t, t = function() {
				return e
			});
			for (var o = a.length, u = new Array(o), l = new Array(o), s = new Array(o), c = 0; c < o; ++c) {
				var f = i[c],
					h = a[c],
					p = h.length,
					g = Ho(t.call(f, f && f.__data__, c, i)),
					d = g.length,
					m = l[c] = new Array(d),
					v = u[c] = new Array(d);
				r(f, h, m, v, s[c] = new Array(p), g, n);
				for (var y, b, w = 0, _ = 0; w < d; ++w)
					if (y = m[w]) {
						for (w >= _ && (_ = w + 1); !(b = v[_]) && ++_ < d;)
							;
						y._next = b || null
					}
			}
			return (u = new Eu(u, i))._enter = l, u._exit = s, u
		},
		enter: function() {
			return new Eu(this._enter || this._groups.map(jo), this._parents)
		},
		exit: function() {
			return new Eu(this._exit || this._groups.map(jo), this._parents)
		},
		join: function(t, n, e) {
			var r = this.enter(),
				i = this,
				a = this.exit();
			return r = "function" == typeof t ? t(r) : r.append(t + ""), null != n && (i = n(i)), null == e ? a.remove() : e(a), r && i ? r.merge(i).order() : i
		},
		merge: function(t) {
			if (!(t instanceof Eu))
				throw new Error("invalid merge");
			for (var n = this._groups, e = t._groups, r = n.length, i = e.length, a = Math.min(r, i), o = new Array(r), u = 0; u < a; ++u)
				for (var l, s = n[u], c = e[u], f = s.length, h = o[u] = new Array(f), p = 0; p < f; ++p)
					(l = s[p] || c[p]) && (h[p] = l);
			for (; u < r; ++u)
				o[u] = n[u];
			return new Eu(o, this._parents)
		},
		selection: function() {
			return this
		},
		order: function() {
			for (var t = this._groups, n = -1, e = t.length; ++n < e;)
				for (var r, i = t[n], a = i.length - 1, o = i[a]; --a >= 0;)
					(r = i[a]) && (o && 4 ^ r.compareDocumentPosition(o) && o.parentNode.insertBefore(r, o), o = r);
			return this
		},
		sort: function(t) {
			function n(n, e) {
				return n && e ? t(n.__data__, e.__data__) : !n - !e
			}
			t || (t = Xo);
			for (var e = this._groups, r = e.length, i = new Array(r), a = 0; a < r; ++a) {
				for (var o, u = e[a], l = u.length, s = i[a] = new Array(l), c = 0; c < l; ++c)
					(o = u[c]) && (s[c] = o);
				s.sort(n)
			}
			return new Eu(i, this._parents).order()
		},
		call: function() {
			var t = arguments[0];
			return arguments[0] = this, t.apply(null, arguments), this
		},
		nodes: function() {
			return Array.from(this)
		},
		node: function() {
			for (var t = this._groups, n = 0, e = t.length; n < e; ++n)
				for (var r = t[n], i = 0, a = r.length; i < a; ++i) {
					var o = r[i];
					if (o)
						return o
				}
			return null
		},
		size: function() {
			let t = 0;
			for (const n of this)
				++t;
			return t
		},
		empty: function() {
			return !this.node()
		},
		each: function(t) {
			for (var n = this._groups, e = 0, r = n.length; e < r; ++e)
				for (var i, a = n[e], o = 0, u = a.length; o < u; ++o)
					(i = a[o]) && t.call(i, i.__data__, o, a);
			return this
		},
		attr: function(t, n) {
			var e = To(t);
			if (arguments.length < 2) {
				var r = this.node();
				return e.local ? r.getAttributeNS(e.space, e.local) : r.getAttribute(e)
			}
			return this.each((null == n ? e.local ? Wo : Vo : "function" == typeof n ? e.local ? Jo : Qo : e.local ? Zo : Go)(e, n))
		},
		style: function(t, n, e) {
			return arguments.length > 1 ? this.each((null == n ? tu : "function" == typeof n ? eu : nu)(t, n, null == e ? "" : e)) : function(t, n) {
				return t.style.getPropertyValue(n) || Ko(t).getComputedStyle(t, null).getPropertyValue(n)
			}(this.node(), t)
		},
		property: function(t, n) {
			return arguments.length > 1 ? this.each((null == n ? ru : "function" == typeof n ? au : iu)(t, n)) : this.node()[t]
		},
		classed: function(t, n) {
			var e = ou(t + "");
			if (arguments.length < 2) {
				for (var r = uu(this.node()), i = -1, a = e.length; ++i < a;)
					if (!r.contains(e[i]))
						return !1;
				return !0
			}
			return this.each(("function" == typeof n ? pu : n ? fu : hu)(e, n))
		},
		text: function(t) {
			return arguments.length ? this.each(null == t ? gu : ("function" == typeof t ? mu : du)(t)) : this.node().textContent
		},
		html: function(t) {
			return arguments.length ? this.each(null == t ? vu : ("function" == typeof t ? bu : yu)(t)) : this.node().innerHTML
		},
		raise: function() {
			return this.each(wu)
		},
		lower: function() {
			return this.each(_u)
		},
		append: function(t) {
			var n = "function" == typeof t ? t : zo(t);
			return this.select((function() {
				return this.appendChild(n.apply(this, arguments))
			}))
		},
		insert: function(t, n) {
			var e = "function" == typeof t ? t : zo(t),
				r = null == n ? xu : "function" == typeof n ? n : Fo(n);
			return this.select((function() {
				return this.insertBefore(e.apply(this, arguments), r.apply(this, arguments) || null)
			}))
		},
		remove: function() {
			return this.each(Mu)
		},
		clone: function(t) {
			return this.select(t ? Su : Au)
		},
		datum: function(t) {
			return arguments.length ? this.property("__data__", t) : this.node().__data__
		},
		on: function(t, n, e) {
			var r,
				i,
				a = function(t) {
					return t.trim().split(/^|\s+/).map((function(t) {
						var n = "",
							e = t.indexOf(".");
						return e >= 0 && (n = t.slice(e + 1), t = t.slice(0, e)), {
							type: t,
							name: n
						}
					}))
				}(t + ""),
				o = a.length;
			if (!(arguments.length < 2)) {
				for (u = n ? Cu : ku, r = 0; r < o; ++r)
					this.each(u(a[r], n, e));
				return this
			}
			var u = this.node().__on;
			if (u)
				for (var l, s = 0, c = u.length; s < c; ++s)
					for (r = 0, l = u[s]; r < o; ++r)
						if ((i = a[r]).type === l.type && i.name === l.name)
							return l.value
		},
		dispatch: function(t, n) {
			return this.each(("function" == typeof n ? Nu : Du)(t, n))
		},
		[Symbol.iterator]: function* () {
			for (var t = this._groups, n = 0, e = t.length; n < e; ++n)
				for (var r, i = t[n], a = 0, o = i.length; a < o; ++a)
					(r = i[a]) && (yield r)
		}
	};
	var Lu = /^\s+/,
		Uu = /\s+$/;
	function Ru(t, n) {
		if (n = n || {}, (t = t || "") instanceof Ru)
			return t;
		if (!(this instanceof Ru))
			return new Ru(t, n);
		var e = function(t) {
			var n = {
					r: 0,
					g: 0,
					b: 0
				},
				e = 1,
				r = null,
				i = null,
				a = null,
				o = !1,
				u = !1;
			"string" == typeof t && (t = function(t) {
				t = t.replace(Lu, "").replace(Uu, "").toLowerCase();
				var n,
					e = !1;
				if (tl[t])
					t = tl[t],
					e = !0;
				else if ("transparent" == t)
					return {
						r: 0,
						g: 0,
						b: 0,
						a: 0,
						format: "name"
					};
				if (n = pl.rgb.exec(t))
					return {
						r: n[1],
						g: n[2],
						b: n[3]
					};
				if (n = pl.rgba.exec(t))
					return {
						r: n[1],
						g: n[2],
						b: n[3],
						a: n[4]
					};
				if (n = pl.hsl.exec(t))
					return {
						h: n[1],
						s: n[2],
						l: n[3]
					};
				if (n = pl.hsla.exec(t))
					return {
						h: n[1],
						s: n[2],
						l: n[3],
						a: n[4]
					};
				if (n = pl.hsv.exec(t))
					return {
						h: n[1],
						s: n[2],
						v: n[3]
					};
				if (n = pl.hsva.exec(t))
					return {
						h: n[1],
						s: n[2],
						v: n[3],
						a: n[4]
					};
				if (n = pl.hex8.exec(t))
					return {
						r: al(n[1]),
						g: al(n[2]),
						b: al(n[3]),
						a: sl(n[4]),
						format: e ? "name" : "hex8"
					};
				if (n = pl.hex6.exec(t))
					return {
						r: al(n[1]),
						g: al(n[2]),
						b: al(n[3]),
						format: e ? "name" : "hex"
					};
				if (n = pl.hex4.exec(t))
					return {
						r: al(n[1] + "" + n[1]),
						g: al(n[2] + "" + n[2]),
						b: al(n[3] + "" + n[3]),
						a: sl(n[4] + "" + n[4]),
						format: e ? "name" : "hex8"
					};
				if (n = pl.hex3.exec(t))
					return {
						r: al(n[1] + "" + n[1]),
						g: al(n[2] + "" + n[2]),
						b: al(n[3] + "" + n[3]),
						format: e ? "name" : "hex"
					};
				return !1
			}(t));
			"object" == Hu(t) && (gl(t.r) && gl(t.g) && gl(t.b) ? (l = t.r, s = t.g, c = t.b, n = {
				r: 255 * rl(l, 255),
				g: 255 * rl(s, 255),
				b: 255 * rl(c, 255)
			}, o = !0, u = "%" === String(t.r).substr(-1) ? "prgb" : "rgb") : gl(t.h) && gl(t.s) && gl(t.v) ? (r = ul(t.s), i = ul(t.v), n = function(t, n, e) {
				t = 6 * rl(t, 360),
				n = rl(n, 100),
				e = rl(e, 100);
				var r = Math.floor(t),
					i = t - r,
					a = e * (1 - n),
					o = e * (1 - i * n),
					u = e * (1 - (1 - i) * n),
					l = r % 6,
					s = [e, o, a, a, u, e][l],
					c = [u, e, e, o, a, a][l],
					f = [a, a, u, e, e, o][l];
				return {
					r: 255 * s,
					g: 255 * c,
					b: 255 * f
				}
			}(t.h, r, i), o = !0, u = "hsv") : gl(t.h) && gl(t.s) && gl(t.l) && (r = ul(t.s), a = ul(t.l), n = function(t, n, e) {
				var r,
					i,
					a;
				function o(t, n, e) {
					return e < 0 && (e += 1), e > 1 && (e -= 1), e < 1 / 6 ? t + 6 * (n - t) * e : e < .5 ? n : e < 2 / 3 ? t + (n - t) * (2 / 3 - e) * 6 : t
				}
				if (t = rl(t, 360), n = rl(n, 100), e = rl(e, 100), 0 === n)
					r = i = a = e;
				else {
					var u = e < .5 ? e * (1 + n) : e + n - e * n,
						l = 2 * e - u;
					r = o(l, u, t + 1 / 3),
					i = o(l, u, t),
					a = o(l, u, t - 1 / 3)
				}
				return {
					r: 255 * r,
					g: 255 * i,
					b: 255 * a
				}
			}(t.h, r, a), o = !0, u = "hsl"), t.hasOwnProperty("a") && (e = t.a));
			var l,
				s,
				c;
			return e = el(e), {
				ok: o,
				format: t.format || u,
				r: Math.min(255, Math.max(n.r, 0)),
				g: Math.min(255, Math.max(n.g, 0)),
				b: Math.min(255, Math.max(n.b, 0)),
				a: e
			}
		}(t);
		this._originalInput = t,
		this._r = e.r,
		this._g = e.g,
		this._b = e.b,
		this._a = e.a,
		this._roundA = Math.round(100 * this._a) / 100,
		this._format = n.format || e.format,
		this._gradientType = n.gradientType,
		this._r < 1 && (this._r = Math.round(this._r)),
		this._g < 1 && (this._g = Math.round(this._g)),
		this._b < 1 && (this._b = Math.round(this._b)),
		this._ok = e.ok
	}
	function Yu(t, n, e) {
		t = rl(t, 255),
		n = rl(n, 255),
		e = rl(e, 255);
		var r,
			i,
			a = Math.max(t, n, e),
			o = Math.min(t, n, e),
			u = (a + o) / 2;
		if (a == o)
			r = i = 0;
		else {
			var l = a - o;
			switch (i = u > .5 ? l / (2 - a - o) : l / (a + o), a) {
			case t:
				r = (n - e) / l + (n < e ? 6 : 0);
				break;
			case n:
				r = (e - t) / l + 2;
				break;
			case e:
				r = (t - n) / l + 4
			}
			r /= 6
		}
		return {
			h: r,
			s: i,
			l: u
		}
	}
	function Ou(t, n, e) {
		t = rl(t, 255),
		n = rl(n, 255),
		e = rl(e, 255);
		var r,
			i,
			a = Math.max(t, n, e),
			o = Math.min(t, n, e),
			u = a,
			l = a - o;
		if (i = 0 === a ? 0 : l / a, a == o)
			r = 0;
		else {
			switch (a) {
			case t:
				r = (n - e) / l + (n < e ? 6 : 0);
				break;
			case n:
				r = (e - t) / l + 2;
				break;
			case e:
				r = (t - n) / l + 4
			}
			r /= 6
		}
		return {
			h: r,
			s: i,
			v: u
		}
	}
	function Pu(t, n, e, r) {
		var i = [ol(Math.round(t).toString(16)), ol(Math.round(n).toString(16)), ol(Math.round(e).toString(16))];
		return r && i[0].charAt(0) == i[0].charAt(1) && i[1].charAt(0) == i[1].charAt(1) && i[2].charAt(0) == i[2].charAt(1) ? i[0].charAt(0) + i[1].charAt(0) + i[2].charAt(0) : i.join("")
	}
	function ju(t, n, e, r) {
		return [ol(ll(r)), ol(Math.round(t).toString(16)), ol(Math.round(n).toString(16)), ol(Math.round(e).toString(16))].join("")
	}
	function $u(t, n) {
		n = 0 === n ? 0 : n || 10;
		var e = Ru(t).toHsl();
		return e.s -= n / 100, e.s = il(e.s), Ru(e)
	}
	function Iu(t, n) {
		n = 0 === n ? 0 : n || 10;
		var e = Ru(t).toHsl();
		return e.s += n / 100, e.s = il(e.s), Ru(e)
	}
	function qu(t) {
		return Ru(t).desaturate(100)
	}
	function Bu(t, n) {
		n = 0 === n ? 0 : n || 10;
		var e = Ru(t).toHsl();
		return e.l += n / 100, e.l = il(e.l), Ru(e)
	}
	function Xu(t, n) {
		n = 0 === n ? 0 : n || 10;
		var e = Ru(t).toRgb();
		return e.r = Math.max(0, Math.min(255, e.r - Math.round(-n / 100 * 255))), e.g = Math.max(0, Math.min(255, e.g - Math.round(-n / 100 * 255))), e.b = Math.max(0, Math.min(255, e.b - Math.round(-n / 100 * 255))), Ru(e)
	}
	function Vu(t, n) {
		n = 0 === n ? 0 : n || 10;
		var e = Ru(t).toHsl();
		return e.l -= n / 100, e.l = il(e.l), Ru(e)
	}
	function Wu(t, n) {
		var e = Ru(t).toHsl(),
			r = (e.h + n) % 360;
		return e.h = r < 0 ? 360 + r : r, Ru(e)
	}
	function Gu(t) {
		var n = Ru(t).toHsl();
		return n.h = (n.h + 180) % 360, Ru(n)
	}
	function Zu(t, n) {
		if (isNaN(n) || n <= 0)
			throw new Error("Argument to polyad must be a positive number");
		for (var e = Ru(t).toHsl(), r = [Ru(t)], i = 360 / n, a = 1; a < n; a++)
			r.push(Ru({
				h: (e.h + a * i) % 360,
				s: e.s,
				l: e.l
			}));
		return r
	}
	function Qu(t) {
		var n = Ru(t).toHsl(),
			e = n.h;
		return [Ru(t), Ru({
			h: (e + 72) % 360,
			s: n.s,
			l: n.l
		}), Ru({
			h: (e + 216) % 360,
			s: n.s,
			l: n.l
		})]
	}
	function Ju(t, n, e) {
		n = n || 6,
		e = e || 30;
		var r = Ru(t).toHsl(),
			i = 360 / e,
			a = [Ru(t)];
		for (r.h = (r.h - (i * n >> 1) + 720) % 360; --n;)
			r.h = (r.h + i) % 360,
			a.push(Ru(r));
		return a
	}
	function Ku(t, n) {
		n = n || 6;
		for (var e = Ru(t).toHsv(), r = e.h, i = e.s, a = e.v, o = [], u = 1 / n; n--;)
			o.push(Ru({
				h: r,
				s: i,
				v: a
			})),
			a = (a + u) % 1;
		return o
	}
	Ru.prototype = {
		isDark: function() {
			return this.getBrightness() < 128
		},
		isLight: function() {
			return !this.isDark()
		},
		isValid: function() {
			return this._ok
		},
		getOriginalInput: function() {
			return this._originalInput
		},
		getFormat: function() {
			return this._format
		},
		getAlpha: function() {
			return this._a
		},
		getBrightness: function() {
			var t = this.toRgb();
			return (299 * t.r + 587 * t.g + 114 * t.b) / 1e3
		},
		getLuminance: function() {
			var t,
				n,
				e,
				r = this.toRgb();
			return t = r.r / 255, n = r.g / 255, e = r.b / 255, .2126 * (t <= .03928 ? t / 12.92 : Math.pow((t + .055) / 1.055, 2.4)) + .7152 * (n <= .03928 ? n / 12.92 : Math.pow((n + .055) / 1.055, 2.4)) + .0722 * (e <= .03928 ? e / 12.92 : Math.pow((e + .055) / 1.055, 2.4))
		},
		setAlpha: function(t) {
			return this._a = el(t), this._roundA = Math.round(100 * this._a) / 100, this
		},
		toHsv: function() {
			var t = Ou(this._r, this._g, this._b);
			return {
				h: 360 * t.h,
				s: t.s,
				v: t.v,
				a: this._a
			}
		},
		toHsvString: function() {
			var t = Ou(this._r, this._g, this._b),
				n = Math.round(360 * t.h),
				e = Math.round(100 * t.s),
				r = Math.round(100 * t.v);
			return 1 == this._a ? "hsv(" + n + ", " + e + "%, " + r + "%)" : "hsva(" + n + ", " + e + "%, " + r + "%, " + this._roundA + ")"
		},
		toHsl: function() {
			var t = Yu(this._r, this._g, this._b);
			return {
				h: 360 * t.h,
				s: t.s,
				l: t.l,
				a: this._a
			}
		},
		toHslString: function() {
			var t = Yu(this._r, this._g, this._b),
				n = Math.round(360 * t.h),
				e = Math.round(100 * t.s),
				r = Math.round(100 * t.l);
			return 1 == this._a ? "hsl(" + n + ", " + e + "%, " + r + "%)" : "hsla(" + n + ", " + e + "%, " + r + "%, " + this._roundA + ")"
		},
		toHex: function(t) {
			return Pu(this._r, this._g, this._b, t)
		},
		toHexString: function(t) {
			return "#" + this.toHex(t)
		},
		toHex8: function(t) {
			return function(t, n, e, r, i) {
				var a = [ol(Math.round(t).toString(16)), ol(Math.round(n).toString(16)), ol(Math.round(e).toString(16)), ol(ll(r))];
				if (i && a[0].charAt(0) == a[0].charAt(1) && a[1].charAt(0) == a[1].charAt(1) && a[2].charAt(0) == a[2].charAt(1) && a[3].charAt(0) == a[3].charAt(1))
					return a[0].charAt(0) + a[1].charAt(0) + a[2].charAt(0) + a[3].charAt(0);
				return a.join("")
			}(this._r, this._g, this._b, this._a, t)
		},
		toHex8String: function(t) {
			return "#" + this.toHex8(t)
		},
		toRgb: function() {
			return {
				r: Math.round(this._r),
				g: Math.round(this._g),
				b: Math.round(this._b),
				a: this._a
			}
		},
		toRgbString: function() {
			return 1 == this._a ? "rgb(" + Math.round(this._r) + ", " + Math.round(this._g) + ", " + Math.round(this._b) + ")" : "rgba(" + Math.round(this._r) + ", " + Math.round(this._g) + ", " + Math.round(this._b) + ", " + this._roundA + ")"
		},
		toPercentageRgb: function() {
			return {
				r: Math.round(100 * rl(this._r, 255)) + "%",
				g: Math.round(100 * rl(this._g, 255)) + "%",
				b: Math.round(100 * rl(this._b, 255)) + "%",
				a: this._a
			}
		},
		toPercentageRgbString: function() {
			return 1 == this._a ? "rgb(" + Math.round(100 * rl(this._r, 255)) + "%, " + Math.round(100 * rl(this._g, 255)) + "%, " + Math.round(100 * rl(this._b, 255)) + "%)" : "rgba(" + Math.round(100 * rl(this._r, 255)) + "%, " + Math.round(100 * rl(this._g, 255)) + "%, " + Math.round(100 * rl(this._b, 255)) + "%, " + this._roundA + ")"
		},
		toName: function() {
			return 0 === this._a ? "transparent" : !(this._a < 1) && (nl[Pu(this._r, this._g, this._b, !0)] || !1)
		},
		toFilter: function(t) {
			var n = "#" + ju(this._r, this._g, this._b, this._a),
				e = n,
				r = this._gradientType ? "GradientType = 1, " : "";
			if (t) {
				var i = Ru(t);
				e = "#" + ju(i._r, i._g, i._b, i._a)
			}
			return "progid:DXImageTransform.Microsoft.gradient(" + r + "startColorstr=" + n + ",endColorstr=" + e + ")"
		},
		toString: function(t) {
			var n = !!t;
			t = t || this._format;
			var e = !1,
				r = this._a < 1 && this._a >= 0;
			return n || !r || "hex" !== t && "hex6" !== t && "hex3" !== t && "hex4" !== t && "hex8" !== t && "name" !== t ? ("rgb" === t && (e = this.toRgbString()), "prgb" === t && (e = this.toPercentageRgbString()), "hex" !== t && "hex6" !== t || (e = this.toHexString()), "hex3" === t && (e = this.toHexString(!0)), "hex4" === t && (e = this.toHex8String(!0)), "hex8" === t && (e = this.toHex8String()), "name" === t && (e = this.toName()), "hsl" === t && (e = this.toHslString()), "hsv" === t && (e = this.toHsvString()), e || this.toHexString()) : "name" === t && 0 === this._a ? this.toName() : this.toRgbString()
		},
		clone: function() {
			return Ru(this.toString())
		},
		_applyModification: function(t, n) {
			var e = t.apply(null, [this].concat([].slice.call(n)));
			return this._r = e._r, this._g = e._g, this._b = e._b, this.setAlpha(e._a), this
		},
		lighten: function() {
			return this._applyModification(Bu, arguments)
		},
		brighten: function() {
			return this._applyModification(Xu, arguments)
		},
		darken: function() {
			return this._applyModification(Vu, arguments)
		},
		desaturate: function() {
			return this._applyModification($u, arguments)
		},
		saturate: function() {
			return this._applyModification(Iu, arguments)
		},
		greyscale: function() {
			return this._applyModification(qu, arguments)
		},
		spin: function() {
			return this._applyModification(Wu, arguments)
		},
		_applyCombination: function(t, n) {
			return t.apply(null, [this].concat([].slice.call(n)))
		},
		analogous: function() {
			return this._applyCombination(Ju, arguments)
		},
		complement: function() {
			return this._applyCombination(Gu, arguments)
		},
		monochromatic: function() {
			return this._applyCombination(Ku, arguments)
		},
		splitcomplement: function() {
			return this._applyCombination(Qu, arguments)
		},
		triad: function() {
			return this._applyCombination(Zu, [3])
		},
		tetrad: function() {
			return this._applyCombination(Zu, [4])
		}
	},
	Ru.fromRatio = function(t, n) {
		if ("object" == Hu(t)) {
			var e = {};
			for (var r in t)
				t.hasOwnProperty(r) && (e[r] = "a" === r ? t[r] : ul(t[r]));
			t = e
		}
		return Ru(t, n)
	},
	Ru.equals = function(t, n) {
		return !(!t || !n) && Ru(t).toRgbString() == Ru(n).toRgbString()
	},
	Ru.random = function() {
		return Ru.fromRatio({
			r: Math.random(),
			g: Math.random(),
			b: Math.random()
		})
	},
	Ru.mix = function(t, n, e) {
		e = 0 === e ? 0 : e || 50;
		var r = Ru(t).toRgb(),
			i = Ru(n).toRgb(),
			a = e / 100;
		return Ru({
			r: (i.r - r.r) * a + r.r,
			g: (i.g - r.g) * a + r.g,
			b: (i.b - r.b) * a + r.b,
			a: (i.a - r.a) * a + r.a
		})
	},
	// <http://www.w3.org/TR/2008/REC-WCAG20-20081211/#contrast-ratiodef (WCAG Version 2)
	// Analyze the 2 colors and returns the color contrast defined by (WCAG Version 2)
	Ru.readability = function(t, n) {
		var e = Ru(t),
			r = Ru(n);
		return (Math.max(e.getLuminance(), r.getLuminance()) + .05) / (Math.min(e.getLuminance(), r.getLuminance()) + .05)
	},
	Ru.isReadable = function(t, n, e) {
		var r,
			i,
			a = Ru.readability(t, n);
		switch (i = !1, (r = function(t) {
			var n,
				e;
			n = ((t = t || {
				level: "AA",
				size: "small"
			}).level || "AA").toUpperCase(),
			e = (t.size || "small").toLowerCase(),
			"AA" !== n && "AAA" !== n && (n = "AA");
			"small" !== e && "large" !== e && (e = "small");
			return {
				level: n,
				size: e
			}
		}(e)).level + r.size) {
		case "AAsmall":
		case "AAAlarge":
			i = a >= 4.5;
			break;
		case "AAlarge":
			i = a >= 3;
			break;
		case "AAAsmall":
			i = a >= 7
		}
		return i
	},
	Ru.mostReadable = function(t, n, e) {
		var r,
			i,
			a,
			o,
			u = null,
			l = 0;
		i = (e = e || {}).includeFallbackColors,
		a = e.level,
		o = e.size;
		for (var s = 0; s < n.length; s++)
			(r = Ru.readability(t, n[s])) > l && (l = r, u = Ru(n[s]));
		return Ru.isReadable(t, u, {
			level: a,
			size: o
		}) || !i ? u : (e.includeFallbackColors = !1, Ru.mostReadable(t, ["#fff", "#000"], e))
	};
	var tl = Ru.names = {
			aliceblue: "f0f8ff",
			antiquewhite: "faebd7",
			aqua: "0ff",
			aquamarine: "7fffd4",
			azure: "f0ffff",
			beige: "f5f5dc",
			bisque: "ffe4c4",
			black: "000",
			blanchedalmond: "ffebcd",
			blue: "00f",
			blueviolet: "8a2be2",
			brown: "a52a2a",
			burlywood: "deb887",
			burntsienna: "ea7e5d",
			cadetblue: "5f9ea0",
			chartreuse: "7fff00",
			chocolate: "d2691e",
			coral: "ff7f50",
			cornflowerblue: "6495ed",
			cornsilk: "fff8dc",
			crimson: "dc143c",
			cyan: "0ff",
			darkblue: "00008b",
			darkcyan: "008b8b",
			darkgoldenrod: "b8860b",
			darkgray: "a9a9a9",
			darkgreen: "006400",
			darkgrey: "a9a9a9",
			darkkhaki: "bdb76b",
			darkmagenta: "8b008b",
			darkolivegreen: "556b2f",
			darkorange: "ff8c00",
			darkorchid: "9932cc",
			darkred: "8b0000",
			darksalmon: "e9967a",
			darkseagreen: "8fbc8f",
			darkslateblue: "483d8b",
			darkslategray: "2f4f4f",
			darkslategrey: "2f4f4f",
			darkturquoise: "00ced1",
			darkviolet: "9400d3",
			deeppink: "ff1493",
			deepskyblue: "00bfff",
			dimgray: "696969",
			dimgrey: "696969",
			dodgerblue: "1e90ff",
			firebrick: "b22222",
			floralwhite: "fffaf0",
			forestgreen: "228b22",
			fuchsia: "f0f",
			gainsboro: "dcdcdc",
			ghostwhite: "f8f8ff",
			gold: "ffd700",
			goldenrod: "daa520",
			gray: "808080",
			green: "008000",
			greenyellow: "adff2f",
			grey: "808080",
			honeydew: "f0fff0",
			hotpink: "ff69b4",
			indianred: "cd5c5c",
			indigo: "4b0082",
			ivory: "fffff0",
			khaki: "f0e68c",
			lavender: "e6e6fa",
			lavenderblush: "fff0f5",
			lawngreen: "7cfc00",
			lemonchiffon: "fffacd",
			lightblue: "add8e6",
			lightcoral: "f08080",
			lightcyan: "e0ffff",
			lightgoldenrodyellow: "fafad2",
			lightgray: "d3d3d3",
			lightgreen: "90ee90",
			lightgrey: "d3d3d3",
			lightpink: "ffb6c1",
			lightsalmon: "ffa07a",
			lightseagreen: "20b2aa",
			lightskyblue: "87cefa",
			lightslategray: "789",
			lightslategrey: "789",
			lightsteelblue: "b0c4de",
			lightyellow: "ffffe0",
			lime: "0f0",
			limegreen: "32cd32",
			linen: "faf0e6",
			magenta: "f0f",
			maroon: "800000",
			mediumaquamarine: "66cdaa",
			mediumblue: "0000cd",
			mediumorchid: "ba55d3",
			mediumpurple: "9370db",
			mediumseagreen: "3cb371",
			mediumslateblue: "7b68ee",
			mediumspringgreen: "00fa9a",
			mediumturquoise: "48d1cc",
			mediumvioletred: "c71585",
			midnightblue: "191970",
			mintcream: "f5fffa",
			mistyrose: "ffe4e1",
			moccasin: "ffe4b5",
			navajowhite: "ffdead",
			navy: "000080",
			oldlace: "fdf5e6",
			olive: "808000",
			olivedrab: "6b8e23",
			orange: "ffa500",
			orangered: "ff4500",
			orchid: "da70d6",
			palegoldenrod: "eee8aa",
			palegreen: "98fb98",
			paleturquoise: "afeeee",
			palevioletred: "db7093",
			papayawhip: "ffefd5",
			peachpuff: "ffdab9",
			peru: "cd853f",
			pink: "ffc0cb",
			plum: "dda0dd",
			powderblue: "b0e0e6",
			purple: "800080",
			rebeccapurple: "663399",
			red: "f00",
			rosybrown: "bc8f8f",
			royalblue: "4169e1",
			saddlebrown: "8b4513",
			salmon: "fa8072",
			sandybrown: "f4a460",
			seagreen: "2e8b57",
			seashell: "fff5ee",
			sienna: "a0522d",
			silver: "c0c0c0",
			skyblue: "87ceeb",
			slateblue: "6a5acd",
			slategray: "708090",
			slategrey: "708090",
			snow: "fffafa",
			springgreen: "00ff7f",
			steelblue: "4682b4",
			tan: "d2b48c",
			teal: "008080",
			thistle: "d8bfd8",
			tomato: "ff6347",
			turquoise: "40e0d0",
			violet: "ee82ee",
			wheat: "f5deb3",
			white: "fff",
			whitesmoke: "f5f5f5",
			yellow: "ff0",
			yellowgreen: "9acd32"
		},
		nl = Ru.hexNames = function(t) {
			var n = {};
			for (var e in t)
				t.hasOwnProperty(e) && (n[t[e]] = e);
			return n
		}(tl);
	function el(t) {
		return t = parseFloat(t), (isNaN(t) || t < 0 || t > 1) && (t = 1), t
	}
	function rl(t, n) {
		(function(t) {
			return "string" == typeof t && -1 != t.indexOf(".") && 1 === parseFloat(t)
		})(t) && (t = "100%");
		var e = function(t) {
			return "string" == typeof t && -1 != t.indexOf("%")
		}(t);
		return t = Math.min(n, Math.max(0, parseFloat(t))), e && (t = parseInt(t * n, 10) / 100), Math.abs(t - n) < 1e-6 ? 1 : t % n / parseFloat(n)
	}
	function il(t) {
		return Math.min(1, Math.max(0, t))
	}
	function al(t) {
		return parseInt(t, 16)
	}
	function ol(t) {
		return 1 == t.length ? "0" + t : "" + t
	}
	function ul(t) {
		return t <= 1 && (t = 100 * t + "%"), t
	}
	function ll(t) {
		return Math.round(255 * parseFloat(t)).toString(16)
	}
	function sl(t) {
		return al(t) / 255
	}
	var cl,
		fl,
		hl,
		pl = (fl = "[\\s|\\(]+(" + (cl = "(?:[-\\+]?\\d*\\.\\d+%?)|(?:[-\\+]?\\d+%?)") + ")[,|\\s]+(" + cl + ")[,|\\s]+(" + cl + ")\\s*\\)?", hl = "[\\s|\\(]+(" + cl + ")[,|\\s]+(" + cl + ")[,|\\s]+(" + cl + ")[,|\\s]+(" + cl + ")\\s*\\)?", {
			CSS_UNIT: new RegExp(cl),
			rgb: new RegExp("rgb" + fl),
			rgba: new RegExp("rgba" + hl),
			hsl: new RegExp("hsl" + fl),
			hsla: new RegExp("hsla" + hl),
			hsv: new RegExp("hsv" + fl),
			hsva: new RegExp("hsva" + hl),
			hex3: /^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,
			hex6: /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/,
			hex4: /^#?([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})([0-9a-fA-F]{1})$/,
			hex8: /^#?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$/
		});
	function gl(t) {
		return !!pl.CSS_UNIT.exec(t)
	}
	var dl = s({
			props: {
				width: {},
				height: {},
				scale: {},
				label: {}
			},
			init: function(t, n) {
				n.gradient = xo()(t),
				n.el = Fu(t),
				n.box = n.el.append("rect").attr("x", 0).attr("y", 0).attr("rx", 3).attr("ry", 3).attr("stroke", "black").attr("stroke-width", .5),
				n.unitLabel = n.el.append("text").attr("class", "legendText").style("text-anchor", "middle").style("dominant-baseline", "central"),
				n.labelFitText = So()(n.unitLabel.node()),
				n.startLabel = n.el.append("text").style("text-anchor", "start").style("dominant-baseline", "central"),
				n.startLabelFitText = So()(n.startLabel.node()),
				n.endLabel = n.el.append("text").style("text-anchor", "end").style("dominant-baseline", "central"),
				n.endLabelFitText = So()(n.endLabel.node())
			},
			update: function(t) {
				t.gradient.colorScale(t.scale),
				t.box.attr("width", t.width).attr("height", t.height).style("fill", "url(#".concat(t.gradient.id(), ")")),
				t.unitLabel.text(t.label).attr("x", .5 * t.width).attr("y", .5 * t.height).style("text-anchor", "middle").style("dominant-baseline", "central").style("fill", Ru(t.scale((t.scale.domain()[t.scale.domain().length - 1] - t.scale.domain()[0]) / 2)).isLight() ? "#444" : "#CCC"),
				t.labelFitText.bbox({
					width: .8 * t.width,
					height: .9 * t.height
				}),
				t.startLabel.text(t.scale.domain()[0]).attr("x", .02 * t.width).attr("y", .5 * t.height).style("fill", Ru(t.scale(t.scale.domain()[0])).isLight() ? "#444" : "#CCC"),
				t.startLabelFitText.bbox({
					width: .3 * t.width,
					height: .7 * t.height
				}),
				t.endLabel.text(t.scale.domain()[t.scale.domain().length - 1]).attr("x", .98 * t.width).attr("y", .5 * t.height).style("fill", Ru(t.scale(t.scale.domain()[t.scale.domain().length - 1])).isLight() ? "#444" : "#CCC"),
				t.endLabelFitText.bbox({
					width: .3 * t.width,
					height: .7 * t.height
				})
			}
		}),
		ml = s({
			props: {
				width: {},
				height: {},
				scale: {},
				label: {}
			},
			init: function(t, n) {
				n.el = Fu(t)
			},
			update: function(t) {
				var n = t.width / t.scale.domain().length,
					e = t.el.selectAll(".color-slot").data(t.scale.domain());
				e.exit().remove();
				var r = e.enter().append("g").attr("class", "color-slot");
				r.append("rect").attr("y", 0).attr("rx", 0).attr("ry", 0).attr("stroke-width", 0),
				r.append("text").style("text-anchor", "middle").style("dominant-baseline", "central"),
				r.append("title"),
				(e = e.merge(r)).select("rect").attr("width", n).attr("height", t.height).attr("x", (function(t, e) {
					return n * e
				})).attr("fill", (function(n) {
					return t.scale(n)
				})),
				e.select("text").text((function(t) {
					return t
				})).attr("x", (function(t, e) {
					return n * (e + .5)
				})).attr("y", .5 * t.height).style("fill", (function(n) {
					return Ru(t.scale(n)).isLight() ? "#333" : "#DDD"
				})).each((function(e) {
					So().bbox({
						width: .9 * n,
						height: .8 * t.height
					})(this)
				})),
				e.select("title").text((function(n) {
					return "".concat(n, " ").concat(t.label)
				}))
			}
		}),
		vl = s({
			props: {
				width: {},
				height: {},
				scale: {},
				label: {}
			},
			init: function(t, n) {
				n.legend = Fu(t).append("g").attr("class", "legend")
			},
			update: function(t) {
				if (t.scale) {
					var n = !t.scale.hasOwnProperty("interpolate") && !t.scale.hasOwnProperty("interpolator");
					t.legend.html(""),
					(n ? ml : dl)().width(t.width).height(t.height).scale(t.scale).label(t.label)(t.legend.node())
				}
			}
		}),
		yl = {
			value: () => {}
		};
	function bl() {
		for (var t, n = 0, e = arguments.length, r = {}; n < e; ++n) {
			if (!(t = arguments[n] + "") || t in r || /[\s.]/.test(t))
				throw new Error("illegal type: " + t);
			r[t] = []
		}
		return new wl(r)
	}
	function wl(t) {
		this._ = t
	}
	function _l(t, n) {
		for (var e, r = 0, i = t.length; r < i; ++r)
			if ((e = t[r]).name === n)
				return e.value
	}
	function xl(t, n, e) {
		for (var r = 0, i = t.length; r < i; ++r)
			if (t[r].name === n) {
				t[r] = yl,
				t = t.slice(0, r).concat(t.slice(r + 1));
				break
			}
		return null != e && t.push({
			name: n,
			value: e
		}), t
	}
	wl.prototype = bl.prototype = {
		constructor: wl,
		on: function(t, n) {
			var e,
				r,
				i = this._,
				a = (r = i, (t + "").trim().split(/^|\s+/).map((function(t) {
					var n = "",
						e = t.indexOf(".");
					if (e >= 0 && (n = t.slice(e + 1), t = t.slice(0, e)), t && !r.hasOwnProperty(t))
						throw new Error("unknown type: " + t);
					return {
						type: t,
						name: n
					}
				}))),
				o = -1,
				u = a.length;
			if (!(arguments.length < 2)) {
				if (null != n && "function" != typeof n)
					throw new Error("invalid callback: " + n);
				for (; ++o < u;)
					if (e = (t = a[o]).type)
						i[e] = xl(i[e], t.name, n);
					else if (null == n)
						for (e in i)
							i[e] = xl(i[e], t.name, null);
				return this
			}
			for (; ++o < u;)
				if ((e = (t = a[o]).type) && (e = _l(i[e], t.name)))
					return e
		},
		copy: function() {
			var t = {},
				n = this._;
			for (var e in n)
				t[e] = n[e].slice();
			return new wl(t)
		},
		call: function(t, n) {
			if ((e = arguments.length - 2) > 0)
				for (var e, r, i = new Array(e), a = 0; a < e; ++a)
					i[a] = arguments[a + 2];
			if (!this._.hasOwnProperty(t))
				throw new Error("unknown type: " + t);
			for (a = 0, e = (r = this._[t]).length; a < e; ++a)
				r[a].value.apply(n, i)
		},
		apply: function(t, n, e) {
			if (!this._.hasOwnProperty(t))
				throw new Error("unknown type: " + t);
			for (var r = this._[t], i = 0, a = r.length; i < a; ++i)
				r[i].value.apply(n, e)
		}
	};
	const Ml = {
		capture: !0,
		passive: !1
	};
	function Al(t) {
		t.preventDefault(),
		t.stopImmediatePropagation()
	}
	var Sl,
		kl,
		Cl = 0,
		Tl = 0,
		Dl = 0,
		Nl = 1e3,
		zl = 0,
		El = 0,
		Fl = 0,
		Hl = "object" == typeof performance && performance.now ? performance : Date,
		Ll = "object" == typeof window && window.requestAnimationFrame ? window.requestAnimationFrame.bind(window) : function(t) {
			setTimeout(t, 17)
		};
	function Ul() {
		return El || (Ll(Rl), El = Hl.now() + Fl)
	}
	function Rl() {
		El = 0
	}
	function Yl() {
		this._call = this._time = this._next = null
	}
	function Ol(t, n, e) {
		var r = new Yl;
		return r.restart(t, n, e), r
	}
	function Pl() {
		El = (zl = Hl.now()) + Fl,
		Cl = Tl = 0;
		try {
			!function() {
				Ul(),
				++Cl;
				for (var t, n = Sl; n;)
					(t = El - n._time) >= 0 && n._call.call(void 0, t),
					n = n._next;
				--Cl
			}()
		} finally {
			Cl = 0,
			function() {
				var t,
					n,
					e = Sl,
					r = 1 / 0;
				for (; e;)
					e._call ? (r > e._time && (r = e._time), t = e, e = e._next) : (n = e._next, e._next = null, e = t ? t._next = n : Sl = n);
				kl = t,
				$l(r)
			}(),
			El = 0
		}
	}
	function jl() {
		var t = Hl.now(),
			n = t - zl;
		n > Nl && (Fl -= n, zl = t)
	}
	function $l(t) {
		Cl || (Tl && (Tl = clearTimeout(Tl)), t - El > 24 ? (t < 1 / 0 && (Tl = setTimeout(Pl, t - Hl.now() - Fl)), Dl && (Dl = clearInterval(Dl))) : (Dl || (zl = Hl.now(), Dl = setInterval(jl, Nl)), Cl = 1, Ll(Pl)))
	}
	function Il(t, n, e) {
		var r = new Yl;
		return n = null == n ? 0 : +n, r.restart((e => {
			r.stop(),
			t(e + n)
		}), n, e), r
	}
	Yl.prototype = Ol.prototype = {
		constructor: Yl,
		restart: function(t, n, e) {
			if ("function" != typeof t)
				throw new TypeError("callback is not a function");
			e = (null == e ? Ul() : +e) + (null == n ? 0 : +n),
			this._next || kl === this || (kl ? kl._next = this : Sl = this, kl = this),
			this._call = t,
			this._time = e,
			$l()
		},
		stop: function() {
			this._call && (this._call = null, this._time = 1 / 0, $l())
		}
	};
	var ql = bl("start", "end", "cancel", "interrupt"),
		Bl = [],
		Xl = 0,
		Vl = 1,
		Wl = 2,
		Gl = 3,
		Zl = 4,
		Ql = 5,
		Jl = 6;
	function Kl(t, n, e, r, i, a) {
		var o = t.__transition;
		if (o) {
			if (e in o)
				return
		} else
			t.__transition = {};
		!function(t, n, e) {
			var r,
				i = t.__transition;
			function a(t) {
				e.state = Vl,
				e.timer.restart(o, e.delay, e.time),
				e.delay <= t && o(t - e.delay)
			}
			function o(a) {
				var s,
					c,
					f,
					h;
				if (e.state !== Vl)
					return l();
				for (s in i)
					if ((h = i[s]).name === e.name) {
						if (h.state === Gl)
							return Il(o);
						h.state === Zl ? (h.state = Jl, h.timer.stop(), h.on.call("interrupt", t, t.__data__, h.index, h.group), delete i[s]) : +s < n && (h.state = Jl, h.timer.stop(), h.on.call("cancel", t, t.__data__, h.index, h.group), delete i[s])
					}
				if (Il((function() {
					e.state === Gl && (e.state = Zl, e.timer.restart(u, e.delay, e.time), u(a))
				})), e.state = Wl, e.on.call("start", t, t.__data__, e.index, e.group), e.state === Wl) {
					for (e.state = Gl, r = new Array(f = e.tween.length), s = 0, c = -1; s < f; ++s)
						(h = e.tween[s].value.call(t, t.__data__, e.index, e.group)) && (r[++c] = h);
					r.length = c + 1
				}
			}
			function u(n) {
				for (var i = n < e.duration ? e.ease.call(null, n / e.duration) : (e.timer.restart(l), e.state = Ql, 1), a = -1, o = r.length; ++a < o;)
					r[a].call(t, i);
				e.state === Ql && (e.on.call("end", t, t.__data__, e.index, e.group), l())
			}
			function l() {
				for (var r in e.state = Jl, e.timer.stop(), delete i[n], i)
					return;
				delete t.__transition
			}
			i[n] = e,
			e.timer = Ol(a, 0, e.time)
		}(t, e, {
			name: n,
			index: r,
			group: i,
			on: ql,
			tween: Bl,
			time: a.time,
			delay: a.delay,
			duration: a.duration,
			ease: a.ease,
			timer: null,
			state: Xl
		})
	}
	function ts(t, n) {
		var e = es(t, n);
		if (e.state > Xl)
			throw new Error("too late; already scheduled");
		return e
	}
	function ns(t, n) {
		var e = es(t, n);
		if (e.state > Gl)
			throw new Error("too late; already running");
		return e
	}
	function es(t, n) {
		var e = t.__transition;
		if (!e || !(e = e[n]))
			throw new Error("transition not found");
		return e
	}
	function rs(t, n) {
		var e,
			r,
			i,
			a = t.__transition,
			o = !0;
		if (a) {
			for (i in n = null == n ? null : n + "", a)
				(e = a[i]).name === n ? (r = e.state > Wl && e.state < Ql, e.state = Jl, e.timer.stop(), e.on.call(r ? "interrupt" : "cancel", t, t.__data__, e.index, e.group), delete a[i]) : o = !1;
			o && delete t.__transition
		}
	}
	function is(t, n) {
		var e,
			r;
		return function() {
			var i = ns(this, t),
				a = i.tween;
			if (a !== e)
				for (var o = 0, u = (r = e = a).length; o < u; ++o)
					if (r[o].name === n) {
						(r = r.slice()).splice(o, 1);
						break
					}
			i.tween = r
		}
	}
	function as(t, n, e) {
		var r,
			i;
		if ("function" != typeof e)
			throw new Error;
		return function() {
			var a = ns(this, t),
				o = a.tween;
			if (o !== r) {
				i = (r = o).slice();
				for (var u = {
						name: n,
						value: e
					}, l = 0, s = i.length; l < s; ++l)
					if (i[l].name === n) {
						i[l] = u;
						break
					}
				l === s && i.push(u)
			}
			a.tween = i
		}
	}
	function os(t, n, e) {
		var r = t._id;
		return t.each((function() {
			var t = ns(this, r);
			(t.value || (t.value = {}))[n] = e.apply(this, arguments)
		})), function(t) {
			return es(t, r).value[n]
		}
	}
	function us(t, n) {
		var e;
		return ("number" == typeof n ? Rt : n instanceof ht ? zt : (e = ht(n)) ? (n = e, zt) : jt)(t, n)
	}
	function ls(t) {
		return function() {
			this.removeAttribute(t)
		}
	}
	function ss(t) {
		return function() {
			this.removeAttributeNS(t.space, t.local)
		}
	}
	function cs(t, n, e) {
		var r,
			i,
			a = e + "";
		return function() {
			var o = this.getAttribute(t);
			return o === a ? null : o === r ? i : i = n(r = o, e)
		}
	}
	function fs(t, n, e) {
		var r,
			i,
			a = e + "";
		return function() {
			var o = this.getAttributeNS(t.space, t.local);
			return o === a ? null : o === r ? i : i = n(r = o, e)
		}
	}
	function hs(t, n, e) {
		var r,
			i,
			a;
		return function() {
			var o,
				u,
				l = e(this);
			if (null != l)
				return (o = this.getAttribute(t)) === (u = l + "") ? null : o === r && u === i ? a : (i = u, a = n(r = o, l));
			this.removeAttribute(t)
		}
	}
	function ps(t, n, e) {
		var r,
			i,
			a;
		return function() {
			var o,
				u,
				l = e(this);
			if (null != l)
				return (o = this.getAttributeNS(t.space, t.local)) === (u = l + "") ? null : o === r && u === i ? a : (i = u, a = n(r = o, l));
			this.removeAttributeNS(t.space, t.local)
		}
	}
	function gs(t, n) {
		var e,
			r;
		function i() {
			var i = n.apply(this, arguments);
			return i !== r && (e = (r = i) && function(t, n) {
				return function(e) {
					this.setAttributeNS(t.space, t.local, n.call(this, e))
				}
			}(t, i)), e
		}
		return i._value = n, i
	}
	function ds(t, n) {
		var e,
			r;
		function i() {
			var i = n.apply(this, arguments);
			return i !== r && (e = (r = i) && function(t, n) {
				return function(e) {
					this.setAttribute(t, n.call(this, e))
				}
			}(t, i)), e
		}
		return i._value = n, i
	}
	function ms(t, n) {
		return function() {
			ts(this, t).delay = +n.apply(this, arguments)
		}
	}
	function vs(t, n) {
		return n = +n, function() {
			ts(this, t).delay = n
		}
	}
	function ys(t, n) {
		return function() {
			ns(this, t).duration = +n.apply(this, arguments)
		}
	}
	function bs(t, n) {
		return n = +n, function() {
			ns(this, t).duration = n
		}
	}
	var ws = na.prototype.constructor;
	function _s(t) {
		return function() {
			this.style.removeProperty(t)
		}
	}
	var xs = 0;
	function Ms(t, n, e, r) {
		this._groups = t,
		this._parents = n,
		this._name = e,
		this._id = r
	}
	function As() {
		return ++xs
	}
	var Ss = na.prototype;
	Ms.prototype = {
		constructor: Ms,
		select: function(t) {
			var n = this._name,
				e = this._id;
			"function" != typeof t && (t = Qr(t));
			for (var r = this._groups, i = r.length, a = new Array(i), o = 0; o < i; ++o)
				for (var u, l, s = r[o], c = s.length, f = a[o] = new Array(c), h = 0; h < c; ++h)
					(u = s[h]) && (l = t.call(u, u.__data__, h, s)) && ("__data__" in u && (l.__data__ = u.__data__), f[h] = l, Kl(f[h], n, e, h, f, es(u, e)));
			return new Ms(a, this._parents, n, e)
		},
		selectAll: function(t) {
			var n = this._name,
				e = this._id;
			"function" != typeof t && (t = Kr(t));
			for (var r = this._groups, i = r.length, a = [], o = [], u = 0; u < i; ++u)
				for (var l, s = r[u], c = s.length, f = 0; f < c; ++f)
					if (l = s[f]) {
						for (var h, p = t.call(l, l.__data__, f, s), g = es(l, e), d = 0, m = p.length; d < m; ++d)
							(h = p[d]) && Kl(h, n, e, d, p, g);
						a.push(p),
						o.push(l)
					}
			return new Ms(a, o, n, e)
		},
		selectChild: Ss.selectChild,
		selectChildren: Ss.selectChildren,
		filter: function(t) {
			"function" != typeof t && (t = ni(t));
			for (var n = this._groups, e = n.length, r = new Array(e), i = 0; i < e; ++i)
				for (var a, o = n[i], u = o.length, l = r[i] = [], s = 0; s < u; ++s)
					(a = o[s]) && t.call(a, a.__data__, s, o) && l.push(a);
			return new Ms(r, this._parents, this._name, this._id)
		},
		merge: function(t) {
			if (t._id !== this._id)
				throw new Error;
			for (var n = this._groups, e = t._groups, r = n.length, i = e.length, a = Math.min(r, i), o = new Array(r), u = 0; u < a; ++u)
				for (var l, s = n[u], c = e[u], f = s.length, h = o[u] = new Array(f), p = 0; p < f; ++p)
					(l = s[p] || c[p]) && (h[p] = l);
			for (; u < r; ++u)
				o[u] = n[u];
			return new Ms(o, this._parents, this._name, this._id)
		},
		selection: function() {
			return new ws(this._groups, this._parents)
		},
		transition: function() {
			for (var t = this._name, n = this._id, e = As(), r = this._groups, i = r.length, a = 0; a < i; ++a)
				for (var o, u = r[a], l = u.length, s = 0; s < l; ++s)
					if (o = u[s]) {
						var c = es(o, n);
						Kl(o, t, e, s, u, {
							time: c.time + c.delay + c.duration,
							delay: 0,
							duration: c.duration,
							ease: c.ease
						})
					}
			return new Ms(r, this._parents, t, e)
		},
		call: Ss.call,
		nodes: Ss.nodes,
		node: Ss.node,
		size: Ss.size,
		empty: Ss.empty,
		each: Ss.each,
		on: function(t, n) {
			var e = this._id;
			return arguments.length < 2 ? es(this.node(), e).on.on(t) : this.each(function(t, n, e) {
				var r,
					i,
					a = function(t) {
						return (t + "").trim().split(/^|\s+/).every((function(t) {
							var n = t.indexOf(".");
							return n >= 0 && (t = t.slice(0, n)), !t || "start" === t
						}))
					}(n) ? ts : ns;
				return function() {
					var o = a(this, t),
						u = o.on;
					u !== r && (i = (r = u).copy()).on(n, e),
					o.on = i
				}
			}(e, t, n))
		},
		attr: function(t, n) {
			var e = Xr(t),
				r = "transform" === e ? Zt : us;
			return this.attrTween(t, "function" == typeof n ? (e.local ? ps : hs)(e, r, os(this, "attr." + t, n)) : null == n ? (e.local ? ss : ls)(e) : (e.local ? fs : cs)(e, r, n))
		},
		attrTween: function(t, n) {
			var e = "attr." + t;
			if (arguments.length < 2)
				return (e = this.tween(e)) && e._value;
			if (null == n)
				return this.tween(e, null);
			if ("function" != typeof n)
				throw new Error;
			var r = Xr(t);
			return this.tween(e, (r.local ? gs : ds)(r, n))
		},
		style: function(t, n, e) {
			var r = "transform" == (t += "") ? Gt : us;
			return null == n ? this.styleTween(t, function(t, n) {
				var e,
					r,
					i;
				return function() {
					var a = Ai(this, t),
						o = (this.style.removeProperty(t), Ai(this, t));
					return a === o ? null : a === e && o === r ? i : i = n(e = a, r = o)
				}
			}(t, r)).on("end.style." + t, _s(t)) : "function" == typeof n ? this.styleTween(t, function(t, n, e) {
				var r,
					i,
					a;
				return function() {
					var o = Ai(this, t),
						u = e(this),
						l = u + "";
					return null == u && (this.style.removeProperty(t), l = u = Ai(this, t)), o === l ? null : o === r && l === i ? a : (i = l, a = n(r = o, u))
				}
			}(t, r, os(this, "style." + t, n))).each(function(t, n) {
				var e,
					r,
					i,
					a,
					o = "style." + n,
					u = "end." + o;
				return function() {
					var l = ns(this, t),
						s = l.on,
						c = null == l.value[o] ? a || (a = _s(n)) : void 0;
					s === e && i === c || (r = (e = s).copy()).on(u, i = c),
					l.on = r
				}
			}(this._id, t)) : this.styleTween(t, function(t, n, e) {
				var r,
					i,
					a = e + "";
				return function() {
					var o = Ai(this, t);
					return o === a ? null : o === r ? i : i = n(r = o, e)
				}
			}(t, r, n), e).on("end.style." + t, null)
		},
		styleTween: function(t, n, e) {
			var r = "style." + (t += "");
			if (arguments.length < 2)
				return (r = this.tween(r)) && r._value;
			if (null == n)
				return this.tween(r, null);
			if ("function" != typeof n)
				throw new Error;
			return this.tween(r, function(t, n, e) {
				var r,
					i;
				function a() {
					var a = n.apply(this, arguments);
					return a !== i && (r = (i = a) && function(t, n, e) {
						return function(r) {
							this.style.setProperty(t, n.call(this, r), e)
						}
					}(t, a, e)), r
				}
				return a._value = n, a
			}(t, n, null == e ? "" : e))
		},
		text: function(t) {
			return this.tween("text", "function" == typeof t ? function(t) {
				return function() {
					var n = t(this);
					this.textContent = null == n ? "" : n
				}
			}(os(this, "text", t)) : function(t) {
				return function() {
					this.textContent = t
				}
			}(null == t ? "" : t + ""))
		},
		textTween: function(t) {
			var n = "text";
			if (arguments.length < 1)
				return (n = this.tween(n)) && n._value;
			if (null == t)
				return this.tween(n, null);
			if ("function" != typeof t)
				throw new Error;
			return this.tween(n, function(t) {
				var n,
					e;
				function r() {
					var r = t.apply(this, arguments);
					return r !== e && (n = (e = r) && function(t) {
						return function(n) {
							this.textContent = t.call(this, n)
						}
					}(r)), n
				}
				return r._value = t, r
			}(t))
		},
		remove: function() {
			return this.on("end.remove", function(t) {
				return function() {
					var n = this.parentNode;
					for (var e in this.__transition)
						if (+e !== t)
							return;
					n && n.removeChild(this)
				}
			}(this._id))
		},
		tween: function(t, n) {
			var e = this._id;
			if (t += "", arguments.length < 2) {
				for (var r, i = es(this.node(), e).tween, a = 0, o = i.length; a < o; ++a)
					if ((r = i[a]).name === t)
						return r.value;
				return null
			}
			return this.each((null == n ? is : as)(e, t, n))
		},
		delay: function(t) {
			var n = this._id;
			return arguments.length ? this.each(("function" == typeof t ? ms : vs)(n, t)) : es(this.node(), n).delay
		},
		duration: function(t) {
			var n = this._id;
			return arguments.length ? this.each(("function" == typeof t ? ys : bs)(n, t)) : es(this.node(), n).duration
		},
		ease: function(t) {
			var n = this._id;
			return arguments.length ? this.each(function(t, n) {
				if ("function" != typeof n)
					throw new Error;
				return function() {
					ns(this, t).ease = n
				}
			}(n, t)) : es(this.node(), n).ease
		},
		easeVarying: function(t) {
			if ("function" != typeof t)
				throw new Error;
			return this.each(function(t, n) {
				return function() {
					var e = n.apply(this, arguments);
					if ("function" != typeof e)
						throw new Error;
					ns(this, t).ease = e
				}
			}(this._id, t))
		},
		end: function() {
			var t,
				n,
				e = this,
				r = e._id,
				i = e.size();
			return new Promise((function(a, o) {
				var u = {
						value: o
					},
					l = {
						value: function() {
							0 == --i && a()
						}
					};
				e.each((function() {
					var e = ns(this, r),
						i = e.on;
					i !== t && ((n = (t = i).copy())._.cancel.push(u), n._.interrupt.push(u), n._.end.push(l)),
					e.on = n
				})),
				0 === i && a()
			}))
		},
		[Symbol.iterator]: Ss[Symbol.iterator]
	};
	var ks = {
		time: null,
		delay: 0,
		duration: 250,
		ease: function(t) {
			return ((t *= 2) <= 1 ? t * t * t : (t -= 2) * t * t + 2) / 2
		}
	};
	function Cs(t, n) {
		for (var e; !(e = t.__transition) || !(e = e[n]);)
			if (!(t = t.parentNode))
				throw new Error(`transition ${n} not found`);
		return e
	}
	na.prototype.interrupt = function(t) {
		return this.each((function() {
			rs(this, t)
		}))
	},
	na.prototype.transition = function(t) {
		var n,
			e;
		t instanceof Ms ? (n = t._id, t = t._name) : (n = As(), (e = ks).time = Ul(), t = null == t ? null : t + "");
		for (var r = this._groups, i = r.length, a = 0; a < i; ++a)
			for (var o, u = r[a], l = u.length, s = 0; s < l; ++s)
				(o = u[s]) && Kl(o, t, n, s, u, e || Cs(o, n));
		return new Ms(r, this._parents, t, n)
	};
	var Ts = t => () => t;
	function Ds(t, {sourceEvent: n, target: e, selection: r, mode: i, dispatch: a}) {
		Object.defineProperties(this, {
			type: {
				value: t,
				enumerable: !0,
				configurable: !0
			},
			sourceEvent: {
				value: n,
				enumerable: !0,
				configurable: !0
			},
			target: {
				value: e,
				enumerable: !0,
				configurable: !0
			},
			selection: {
				value: r,
				enumerable: !0,
				configurable: !0
			},
			mode: {
				value: i,
				enumerable: !0,
				configurable: !0
			},
			_: {
				value: a
			}
		})
	}
	function Ns(t) {
		t.preventDefault(),
		t.stopImmediatePropagation()
	}
	var zs = {
			name: "drag"
		},
		Es = {
			name: "space"
		},
		Fs = {
			name: "handle"
		},
		Hs = {
			name: "center"
		};
	const {abs: Ls, max: Us, min: Rs} = Math;
	function Ys(t) {
		return [+t[0], +t[1]]
	}
	function Os(t) {
		return [Ys(t[0]), Ys(t[1])]
	}
	var Ps = {
			name: "x",
			handles: ["w", "e"].map(Vs),
			input: function(t, n) {
				return null == t ? null : [[+t[0], n[0][1]], [+t[1], n[1][1]]]
			},
			output: function(t) {
				return t && [t[0][0], t[1][0]]
			}
		},
		js = {
			name: "y",
			handles: ["n", "s"].map(Vs),
			input: function(t, n) {
				return null == t ? null : [[n[0][0], +t[0]], [n[1][0], +t[1]]]
			},
			output: function(t) {
				return t && [t[0][1], t[1][1]]
			}
		},
		$s = {
			overlay: "crosshair",
			selection: "move",
			n: "ns-resize",
			e: "ew-resize",
			s: "ns-resize",
			w: "ew-resize",
			nw: "nwse-resize",
			ne: "nesw-resize",
			se: "nwse-resize",
			sw: "nesw-resize"
		},
		Is = {
			e: "w",
			w: "e",
			nw: "ne",
			ne: "nw",
			se: "sw",
			sw: "se"
		},
		qs = {
			n: "s",
			s: "n",
			nw: "sw",
			ne: "se",
			se: "ne",
			sw: "nw"
		},
		Bs = {
			overlay: 1,
			selection: 1,
			n: null,
			e: 1,
			s: null,
			w: -1,
			nw: -1,
			ne: 1,
			se: 1,
			sw: -1
		},
		Xs = {
			overlay: 1,
			selection: 1,
			n: -1,
			e: null,
			s: 1,
			w: null,
			nw: -1,
			ne: -1,
			se: 1,
			sw: 1
		};
	function Vs(t) {
		return {
			type: t
		}
	}
	function Ws(t) {
		return !t.ctrlKey && !t.button
	}
	function Gs() {
		var t = this.ownerSVGElement || this;
		return t.hasAttribute("viewBox") ? [[(t = t.viewBox.baseVal).x, t.y], [t.x + t.width, t.y + t.height]] : [[0, 0], [t.width.baseVal.value, t.height.baseVal.value]]
	}
	function Zs() {
		return navigator.maxTouchPoints || "ontouchstart" in this
	}
	function Qs(t) {
		for (; !t.__brush;)
			if (!(t = t.parentNode))
				return;
		return t.__brush
	}
	function Js() {
		return function(t) {
			var n,
				e = Gs,
				r = Ws,
				i = Zs,
				a = !0,
				o = bl("start", "brush", "end"),
				u = 6;
			function l(n) {
				var e = n.property("__brush", d).selectAll(".overlay").data([Vs("overlay")]);
				e.enter().append("rect").attr("class", "overlay").attr("pointer-events", "all").attr("cursor", $s.overlay).merge(e).each((function() {
					var t = Qs(this).extent;
					ea(this).attr("x", t[0][0]).attr("y", t[0][1]).attr("width", t[1][0] - t[0][0]).attr("height", t[1][1] - t[0][1])
				})),
				n.selectAll(".selection").data([Vs("selection")]).enter().append("rect").attr("class", "selection").attr("cursor", $s.selection).attr("fill", "#777").attr("fill-opacity", .3).attr("stroke", "#fff").attr("shape-rendering", "crispEdges");
				var r = n.selectAll(".handle").data(t.handles, (function(t) {
					return t.type
				}));
				r.exit().remove(),
				r.enter().append("rect").attr("class", (function(t) {
					return "handle handle--" + t.type
				})).attr("cursor", (function(t) {
					return $s[t.type]
				})),
				n.each(s).attr("fill", "none").attr("pointer-events", "all").on("mousedown.brush", h).filter(i).on("touchstart.brush", h).on("touchmove.brush", p).on("touchend.brush touchcancel.brush", g).style("touch-action", "none").style("-webkit-tap-highlight-color", "rgba(0,0,0,0)")
			}
			function s() {
				var t = ea(this),
					n = Qs(this).selection;
				n ? (t.selectAll(".selection").style("display", null).attr("x", n[0][0]).attr("y", n[0][1]).attr("width", n[1][0] - n[0][0]).attr("height", n[1][1] - n[0][1]), t.selectAll(".handle").style("display", null).attr("x", (function(t) {
					return "e" === t.type[t.type.length - 1] ? n[1][0] - u / 2 : n[0][0] - u / 2
				})).attr("y", (function(t) {
					return "s" === t.type[0] ? n[1][1] - u / 2 : n[0][1] - u / 2
				})).attr("width", (function(t) {
					return "n" === t.type || "s" === t.type ? n[1][0] - n[0][0] + u : u
				})).attr("height", (function(t) {
					return "e" === t.type || "w" === t.type ? n[1][1] - n[0][1] + u : u
				}))) : t.selectAll(".selection,.handle").style("display", "none").attr("x", null).attr("y", null).attr("width", null).attr("height", null)
			}
			function c(t, n, e) {
				var r = t.__brush.emitter;
				return !r || e && r.clean ? new f(t, n, e) : r
			}
			function f(t, n, e) {
				this.that = t,
				this.args = n,
				this.state = t.__brush,
				this.active = 0,
				this.clean = e
			}
			function h(e) {
				if ((!n || e.touches) && r.apply(this, arguments)) {
					var i,
						o,
						u,
						l,
						f,
						h,
						p,
						g,
						d,
						m,
						v,
						y = this,
						b = e.target.__data__.type,
						w = "selection" === (a && e.metaKey ? b = "overlay" : b) ? zs : a && e.altKey ? Hs : Fs,
						_ = t === js ? null : Bs[b],
						x = t === Ps ? null : Xs[b],
						M = Qs(y),
						A = M.extent,
						S = M.selection,
						k = A[0][0],
						C = A[0][1],
						T = A[1][0],
						D = A[1][1],
						N = 0,
						z = 0,
						E = _ && x && a && e.shiftKey,
						F = Array.from(e.touches || [e], (t => {
							const n = t.identifier;
							return (t = ra(t, y)).point0 = t.slice(), t.identifier = n, t
						}));
					rs(y);
					var H = c(y, arguments, !0).beforestart();
					if ("overlay" === b) {
						S && (d = !0);
						const n = [F[0], F[1] || F[0]];
						M.selection = S = [[i = t === js ? k : Rs(n[0][0], n[1][0]), u = t === Ps ? C : Rs(n[0][1], n[1][1])], [f = t === js ? T : Us(n[0][0], n[1][0]), p = t === Ps ? D : Us(n[0][1], n[1][1])]],
						F.length > 1 && O(e)
					} else
						i = S[0][0],
						u = S[0][1],
						f = S[1][0],
						p = S[1][1];
					o = i,
					l = u,
					h = f,
					g = p;
					var L = ea(y).attr("pointer-events", "none"),
						U = L.selectAll(".overlay").attr("cursor", $s[b]);
					if (e.touches)
						H.moved = Y,
						H.ended = P;
					else {
						var R = ea(e.view).on("mousemove.brush", Y, !0).on("mouseup.brush", P, !0);
						a && R.on("keydown.brush", j, !0).on("keyup.brush", $, !0),
						function(t) {
							var n = t.document.documentElement,
								e = ea(t).on("dragstart.drag", Al, Ml);
							"onselectstart" in n ? e.on("selectstart.drag", Al, Ml) : (n.__noselect = n.style.MozUserSelect, n.style.MozUserSelect = "none")
						}(e.view)
					}
					s.call(y),
					H.start(e, w.name)
				}
				function Y(t) {
					for (const n of t.changedTouches || [t])
						for (const t of F)
							t.identifier === n.identifier && (t.cur = ra(n, y));
					if (E && !m && !v && 1 === F.length) {
						const t = F[0];
						Ls(t.cur[0] - t[0]) > Ls(t.cur[1] - t[1]) ? v = !0 : m = !0
					}
					for (const t of F)
						t.cur && (t[0] = t.cur[0], t[1] = t.cur[1]);
					d = !0,
					Ns(t),
					O(t)
				}
				function O(t) {
					const n = F[0],
						e = n.point0;
					var r;
					switch (N = n[0] - e[0], z = n[1] - e[1], w) {
					case Es:
					case zs:
						_ && (N = Us(k - i, Rs(T - f, N)), o = i + N, h = f + N),
						x && (z = Us(C - u, Rs(D - p, z)), l = u + z, g = p + z);
						break;
					case Fs:
						F[1] ? (_ && (o = Us(k, Rs(T, F[0][0])), h = Us(k, Rs(T, F[1][0])), _ = 1), x && (l = Us(C, Rs(D, F[0][1])), g = Us(C, Rs(D, F[1][1])), x = 1)) : (_ < 0 ? (N = Us(k - i, Rs(T - i, N)), o = i + N, h = f) : _ > 0 && (N = Us(k - f, Rs(T - f, N)), o = i, h = f + N), x < 0 ? (z = Us(C - u, Rs(D - u, z)), l = u + z, g = p) : x > 0 && (z = Us(C - p, Rs(D - p, z)), l = u, g = p + z));
						break;
					case Hs:
						_ && (o = Us(k, Rs(T, i - N * _)), h = Us(k, Rs(T, f + N * _))),
						x && (l = Us(C, Rs(D, u - z * x)), g = Us(C, Rs(D, p + z * x)))
					}
					h < o && (_ *= -1, r = i, i = f, f = r, r = o, o = h, h = r, b in Is && U.attr("cursor", $s[b = Is[b]])),
					g < l && (x *= -1, r = u, u = p, p = r, r = l, l = g, g = r, b in qs && U.attr("cursor", $s[b = qs[b]])),
					M.selection && (S = M.selection),
					m && (o = S[0][0], h = S[1][0]),
					v && (l = S[0][1], g = S[1][1]),
					S[0][0] === o && S[0][1] === l && S[1][0] === h && S[1][1] === g || (M.selection = [[o, l], [h, g]], s.call(y), H.brush(t, w.name))
				}
				function P(t) {
					if (function(t) {
						t.stopImmediatePropagation()
					}(t), t.touches) {
						if (t.touches.length)
							return;
						n && clearTimeout(n),
						n = setTimeout((function() {
							n = null
						}), 500)
					} else
						!function(t, n) {
							var e = t.document.documentElement,
								r = ea(t).on("dragstart.drag", null);
							n && (r.on("click.drag", Al, Ml), setTimeout((function() {
								r.on("click.drag", null)
							}), 0)),
							"onselectstart" in e ? r.on("selectstart.drag", null) : (e.style.MozUserSelect = e.__noselect, delete e.__noselect)
						}(t.view, d),
						R.on("keydown.brush keyup.brush mousemove.brush mouseup.brush", null);
					L.attr("pointer-events", "all"),
					U.attr("cursor", $s.overlay),
					M.selection && (S = M.selection),
					function(t) {
						return t[0][0] === t[1][0] || t[0][1] === t[1][1]
					}(S) && (M.selection = null, s.call(y)),
					H.end(t, w.name)
				}
				function j(t) {
					switch (t.keyCode) {
					case 16:
						E = _ && x;
						break;
					case 18:
						w === Fs && (_ && (f = h - N * _, i = o + N * _), x && (p = g - z * x, u = l + z * x), w = Hs, O(t));
						break;
					case 32:
						w !== Fs && w !== Hs || (_ < 0 ? f = h - N : _ > 0 && (i = o - N), x < 0 ? p = g - z : x > 0 && (u = l - z), w = Es, U.attr("cursor", $s.selection), O(t));
						break;
					default:
						return
					}
					Ns(t)
				}
				function $(t) {
					switch (t.keyCode) {
					case 16:
						E && (m = v = E = !1, O(t));
						break;
					case 18:
						w === Hs && (_ < 0 ? f = h : _ > 0 && (i = o), x < 0 ? p = g : x > 0 && (u = l), w = Fs, O(t));
						break;
					case 32:
						w === Es && (t.altKey ? (_ && (f = h - N * _, i = o + N * _), x && (p = g - z * x, u = l + z * x), w = Hs) : (_ < 0 ? f = h : _ > 0 && (i = o), x < 0 ? p = g : x > 0 && (u = l), w = Fs), U.attr("cursor", $s[b]), O(t));
						break;
					default:
						return
					}
					Ns(t)
				}
			}
			function p(t) {
				c(this, arguments).moved(t)
			}
			function g(t) {
				c(this, arguments).ended(t)
			}
			function d() {
				var n = this.__brush || {
					selection: null
				};
				return n.extent = Os(e.apply(this, arguments)), n.dim = t, n
			}
			return l.move = function(n, e, r) {
				n.tween ? n.on("start.brush", (function(t) {
					c(this, arguments).beforestart().start(t)
				})).on("interrupt.brush end.brush", (function(t) {
					c(this, arguments).end(t)
				})).tween("brush", (function() {
					var n = this,
						r = n.__brush,
						i = c(n, arguments),
						a = r.selection,
						o = t.input("function" == typeof e ? e.apply(this, arguments) : e, r.extent),
						u = $t(a, o);
					function l(t) {
						r.selection = 1 === t && null === o ? null : u(t),
						s.call(n),
						i.brush()
					}
					return null !== a && null !== o ? l : l(1)
				})) : n.each((function() {
					var n = this,
						i = arguments,
						a = n.__brush,
						o = t.input("function" == typeof e ? e.apply(n, i) : e, a.extent),
						u = c(n, i).beforestart();
					rs(n),
					a.selection = null === o ? null : o,
					s.call(n),
					u.start(r).brush(r).end(r)
				}))
			}, l.clear = function(t, n) {
				l.move(t, null, n)
			}, f.prototype = {
				beforestart: function() {
					return 1 == ++this.active && (this.state.emitter = this, this.starting = !0), this
				},
				start: function(t, n) {
					return this.starting ? (this.starting = !1, this.emit("start", t, n)) : this.emit("brush", t), this
				},
				brush: function(t, n) {
					return this.emit("brush", t, n), this
				},
				end: function(t, n) {
					return 0 == --this.active && (delete this.state.emitter, this.emit("end", t, n)), this
				},
				emit: function(n, e, r) {
					var i = ea(this.that).datum();
					o.call(n, this.that, new Ds(n, {
						sourceEvent: e,
						target: l,
						selection: t.output(this.state.selection),
						mode: r,
						dispatch: o
					}), i)
				}
			}, l.extent = function(t) {
				return arguments.length ? (e = "function" == typeof t ? t : Ts(Os(t)), l) : e
			}, l.filter = function(t) {
				return arguments.length ? (r = "function" == typeof t ? t : Ts(!!t), l) : r
			}, l.touchable = function(t) {
				return arguments.length ? (i = "function" == typeof t ? t : Ts(!!t), l) : i
			}, l.handleSize = function(t) {
				return arguments.length ? (u = +t, l) : u
			}, l.keyModifiers = function(t) {
				return arguments.length ? (a = !!t, l) : a
			}, l.on = function() {
				var t = o.on.apply(o, arguments);
				return t === o ? l : t
			}, l
		}(Ps)
	}
	var Ks = s({
		props: {
			width: {
				default: 300
			},
			height: {
				default: 20
			},
			margins: {
				default: {
					top: 0,
					right: 0,
					bottom: 20,
					left: 0
				}
			},
			scale: {},
			domainRange: {},
			currentSelection: {},
			tickFormat: {},
			onChange: {
				default: function(t, n) {}
			}
		},
		init: function(n, e) {
			e.xGrid = P().tickFormat(""),
			e.xAxis = P().tickPadding(0),
			e.brush = Js().handleSize(24).on("end", (function(n) {
				if (n.sourceEvent) {
					var r = n.selection ? n.selection.map(e.scale.invert) : e.scale.domain();
					e.onChange.apply(e, t(r))
				}
			})),
			e.svg = ea(n).append("svg").attr("class", "brusher");
			var r = e.svg.append("g").attr("class", "brusher-margins");
			r.append("rect").attr("class", "grid-background"),
			r.append("g").attr("class", "x grid"),
			r.append("g").attr("class", "x axis"),
			r.append("g").attr("class", "brush")
		},
		update: function(t) {
			if (!(t.domainRange[1] <= t.domainRange[0])) {
				var n = t.width - t.margins.left - t.margins.right,
					e = t.height - t.margins.top - t.margins.bottom;
				t.scale.domain(t.domainRange).range([0, n]),
				t.xAxis.scale(t.scale).tickFormat(t.tickFormat),
				t.xGrid.scale(t.scale).tickSize(-e),
				t.svg.attr("width", t.width).attr("height", t.height),
				t.svg.select(".brusher-margins").attr("transform", "translate(".concat(t.margins.left, ",").concat(t.margins.top, ")")),
				t.svg.select(".grid-background").attr("width", n).attr("height", e),
				t.svg.select(".x.grid").attr("transform", "translate(0," + e + ")").call(t.xGrid),
				t.svg.select(".x.axis").attr("transform", "translate(0," + e + ")").call(t.xAxis).selectAll("text").attr("y", 8),
				t.svg.select(".brush").call(t.brush.extent([[0, 0], [n, e]])).call(t.brush.move, t.currentSelection.map(t.scale))
			}
		}
	});
	function tc(t, n) {
		var e = t.split(/(\d+)/),
			r = n.split(/(\d+)/);
		e.length && "" == e[e.length - 1] && e.pop(),
		r.length && "" == r[r.length - 1] && r.pop();
		for (var i = 0, a = Math.max(e.length, r.length); i < a; i++) {
			if (e.length == i || r.length == i)
				return e.length - r.length;
			if (e[i] != r[i])
				return e[i].match(/\d/) ? +e[i] - +r[i] : e[i].toLowerCase() > r[i].toLowerCase() ? 1 : -1
		}
		return 0
	}
	return s({
		props: {
			data: {
				default: [],
				onChange: function(t, n) {
					!function(t) {
						n.completeStructData = [],
						n.completeFlatData = [],
						n.totalNLines = 0;
						for (var e = 0, r = t.length; e < r; e++) {
							var i = t[e].group;
							n.completeStructData.push({
								group: i,
								lines: t[e].data.map((function(t) {
									return t.label
								}))
							});
							for (var a = 0, o = t[e].data.length; a < o; a++) {
								for (var u = 0, l = t[e].data[a].data.length; u < l; u++) {
									var s = t[e].data[a].data[u],
										c = s.timeRange,
										f = s.val,
										h = s.labelVal;
									n.completeFlatData.push({
										group: i,
										label: t[e].data[a].label,
										timeRange: c.map((function(t) {
											return new Date(t)
										})),
										val: f,
										labelVal: void 0 !== h ? h : f,
										data: t[e].data[a].data[u]
									})
								}
								n.totalNLines++
							}
						}
					}(t),
					n.zoomX = [k(n.completeFlatData, (function(t) {
						return t.timeRange[0]
					})), S(n.completeFlatData, (function(t) {
						return t.timeRange[1]
					}))],
					n.zoomY = [null, null],
					n.overviewArea && n.overviewArea.domainRange(n.zoomX).currentSelection(n.zoomX)
				}
			},
			width: {
				default: window.innerWidth
			},
			maxHeight: {
				default: 640
			},
			maxLineHeight: {
				default: 12
			},
			leftMargin: {
				default: 90
			},
			rightMargin: {
				default: 100
			},
			topMargin: {
				default: 26
			},
			bottomMargin: {
				default: 30
			},
			useUtc: {
				default: !1
			},
			xTickFormat: {},
			dateMarker: {},
			timeFormat: {
				default: "%Y-%m-%d %-I:%M:%S %p",
				triggerUpdate: !1
			},
			zoomX: {
				default: [null, null],
				onChange: function(t, n) {
					n.svg && n.svg.dispatch("zoom", {
						detail: {
							zoomX: t,
							zoomY: null,
							redraw: !1
						}
					})
				}
			},
			zoomY: {
				default: [null, null],
				onChange: function(t, n) {
					n.svg && n.svg.dispatch("zoom", {
						detail: {
							zoomX: null,
							zoomY: t,
							redraw: !1
						}
					})
				}
			},
			minSegmentDuration: {},
			zColorScale: {
				default: Ir(wo)
			},
			zQualitative: {
				default: !1,
				onChange: function(n, e) {
					e.zColorScale = n ? q([].concat(t(yo), t(bo))) : Ir(wo)
				}
			},
			zDataLabel: {
				default: "",
				triggerUpdate: !1
			},
			zScaleLabel: {
				default: "",
				triggerUpdate: !1
			},
			enableOverview: {
				default: !0
			},
			enableAnimations: {
				default: !0,
				onChange: function(t, n) {
					n.transDuration = t ? 700 : 0
				}
			},
			segmentTooltipContent: {
				triggerUpdate: !1
			},
			onZoom: {},
			onLabelClick: {},
			onSegmentClick: {}
		},
		methods: {
			getNLines: function(t) {
				return t.nLines
			},
			getTotalNLines: function(t) {
				return t.totalNLines
			},
			getVisibleStructure: function(t) {
				return t.structData
			},
			getSvg: function(t) {
				return ea(t.svg.node().parentNode).html()
			},
			zoomYLabels: function(t, n) {
				return n ? this.zoomY([r(n[0], !0), r(n[1], !1)]) : [e(t.zoomY[0]), e(t.zoomY[1])];
				function e(n) {
					if (null == n)
						return n;
					for (var e = n, r = 0, i = t.completeStructData.length; r < i; r++) {
						if (t.completeStructData[r].lines.length > e)
							return a(t.completeStructData[r], e);
						e -= t.completeStructData[r].lines.length
					}
					return a(t.completeStructData[t.completeStructData.length - 1], t.completeStructData[t.completeStructData.length - 1].lines.length - 1);
					function a(t, n) {
						return {
							group: t.group,
							label: t.lines[n]
						}
					}
				}
				function r(n, e) {
					var r = (e = e || !1) ? 0 : 1;
					if (null == n)
						return n;
					for (var i = 0, a = 0, o = t.completeStructData.length; a < o; a++) {
						var u = t.grpCmpFunction(n.group, t.completeStructData[a].group);
						if (u < 0)
							break;
						if (0 == u && n.group == t.completeStructData[a].group) {
							for (var l = 0, s = t.completeStructData[a].lines.length; l < s; l++) {
								var c = t.labelCmpFunction(n.label, t.completeStructData[a].lines[l]);
								if (c < 0)
									return i + l - r;
								if (0 == c && n.label == t.completeStructData[a].lines[l])
									return i + l
							}
							return i + t.completeStructData[a].lines.length - r
						}
						i += t.completeStructData[a].lines.length
					}
					return i - r
				}
			},
			sort: function(t, n, e) {
				null == n && (n = t.labelCmpFunction),
				null == e && (e = t.grpCmpFunction),
				t.labelCmpFunction = n,
				t.grpCmpFunction = e,
				t.completeStructData.sort((function(t, n) {
					return e(t.group, n.group)
				}));
				for (var r = 0, i = t.completeStructData.length; r < i; r++)
					t.completeStructData[r].lines.sort(n);
				return t._rerender(), this
			},
			sortAlpha: function(t, n) {
				null == n && (n = !0);
				var e = function(t, e) {
					return tc(n ? t : e, n ? e : t)
				};
				return this.sort(e, e)
			},
			sortChrono: function(t, n) {
				function e(n) {
					for (var e = {}, r = function() {
							var r = n(t.completeFlatData[i]);
							if (e.hasOwnProperty(r))
								return "continue";
							var a = t.completeFlatData.filter((function(t) {
								return r == n(t)
							}));
							e[r] = [k(a, (function(t) {
								return t.timeRange[0]
							})), S(a, (function(t) {
								return t.timeRange[1]
							}))]
						}, i = 0, a = t.completeFlatData.length; i < a; i++)
						r();
					return e
				}
				null == n && (n = !0);
				var r = function(t, n) {
					var e = t[1],
						r = n[1];
					return e && r ? e[1].getTime() == r[1].getTime() ? e[0].getTime() == r[0].getTime() ? tc(t[0], n[0]) : e[0] - r[0] : r[1] - e[1] : null
				};
				function i(t, n) {
					return function(e, i) {
						return r(t(n ? e : i), t(n ? i : e))
					}
				}
				var a = e((function(t) {
						return t.group
					})),
					o = e((function(t) {
						return t.label
					})),
					u = i((function(t) {
						return [t, a[t] || null]
					}), n),
					l = i((function(t) {
						return [t, o[t] || null]
					}), n);
				return this.sort(l, u)
			},
			overviewDomain: function(t, n) {
				return t.enableOverview ? n ? (t.overviewArea.domainRange(n), this) : t.overviewArea.domainRange() : null
			},
			refresh: function(t) {
				return t._rerender(), this
			}
		},
		stateInit: {
			height: null,
			overviewHeight: 20,
			minLabelFont: 2,
			groupBkgGradient: ["#FAFAFA", "#E0E0E0"],
			yScale: null,
			grpScale: null,
			xAxis: null,
			xGrid: null,
			yAxis: null,
			grpAxis: null,
			dateMarkerLine: null,
			svg: null,
			graph: null,
			overviewAreaElem: null,
			overviewArea: null,
			graphW: null,
			graphH: null,
			completeStructData: null,
			structData: null,
			completeFlatData: null,
			flatData: null,
			totalNLines: null,
			nLines: null,
			minSegmentDuration: 0,
			transDuration: 700,
			labelCmpFunction: tc,
			grpCmpFunction: tc
		},
		init: function(t, n) {
			var e,
				r,
				i = ea(t).attr("class", "timelines-chart");
			n.svg = i.append("svg"),
			n.overviewAreaElem = i.append("div"),
			n.yScale = V(),
			n.grpScale = q(),
			n.xAxis = P(),
			n.xGrid = O(D, e),
			n.yAxis = function(t) {
				return O(N, t)
			}(),
			n.grpAxis = function(t) {
				return O(E, t)
			}(),
			function() {
				n.yScale.invert = e,
				n.grpScale.invert = e,
				n.groupGradId = xo().colorScale(An().domain([0, 1]).range(n.groupBkgGradient)).angle(-90)(n.svg.node()).id();
				var t = n.svg.append("g").attr("class", "axises");
				t.append("g").attr("class", "x-axis"),
				t.append("g").attr("class", "x-grid"),
				t.append("g").attr("class", "y-axis"),
				t.append("g").attr("class", "grp-axis"),
				n.yAxis.scale(n.yScale).tickSize(0),
				n.grpAxis.scale(n.grpScale).tickSize(0),
				n.colorLegend = vl()(n.svg.append("g").attr("class", "legendG").node()),
				n.graph = n.svg.append("g"),
				n.dateMarkerLine = n.svg.append("line").attr("class", "x-axis-date-marker"),
				n.enableOverview && (n.overviewArea = Ks().margins({
					top: 1,
					right: 20,
					bottom: 20,
					left: 20
				}).onChange((function(t, e) {
					n.svg.dispatch("zoom", {
						detail: {
							zoomX: [t, e],
							zoomY: null
						}
					})
				})).domainRange(n.zoomX).currentSelection(n.zoomX)(n.overviewAreaElem.node()), n.svg.on("zoomScent", (function(t) {
					var e = t.detail.zoomX;
					n.overviewArea && e && ((e[0] < n.overviewArea.domainRange()[0] || e[1] > n.overviewArea.domainRange()[1]) && n.overviewArea.domainRange([new Date(Math.min(e[0], n.overviewArea.domainRange()[0])), new Date(Math.max(e[1], n.overviewArea.domainRange()[1]))]), n.overviewArea.currentSelection(e))
				})));
				function e(t, n) {
					n = n || function(t, n) {
						return t >= n
					};
					var e = this.domain(),
						r = this.range();
					2 === r.length && 2 !== e.length && (r = C(r[0], r[1], (r[1] - r[0]) / e.length));
					for (var i = r[0], a = 0, o = r.length; a < o; a++)
						if (n(r[a] + i, t))
							return e[Math.round(a * e.length / r.length)];
					return this.domain()[this.domain().length - 1]
				}
			}(),
			n.groupTooltip = mo().attr("class", "chart-tooltip group-tooltip").direction("w").offset([0, 0]).html((function(t, e) {
				var r = e.hasOwnProperty("timeRange") ? n.xScale(e.timeRange[0]) : 0,
					i = e.hasOwnProperty("label") ? n.grpScale(e.group) - n.yScale(e.group + "+&+" + e.label) : 0;
				return n.groupTooltip.offset([i, -r]), e.group
			})),
			n.svg.call(n.groupTooltip),
			n.lineTooltip = mo().attr("class", "chart-tooltip line-tooltip").direction("e").offset([0, 0]).html((function(t, e) {
				var r = e.hasOwnProperty("timeRange") ? n.xScale.range()[1] - n.xScale(e.timeRange[1]) : 0;
				return n.lineTooltip.offset([0, r]), e.label
			})),
			n.svg.call(n.lineTooltip),
			n.segmentTooltip = mo().attr("class", "chart-tooltip segment-tooltip").direction("s").offset([5, 0]).html((function(t, e) {
				if (n.segmentTooltipContent)
					return n.segmentTooltipContent(e);
				var r = n.zColorScale.domain()[n.zColorScale.domain().length - 1] - n.zColorScale.domain()[0],
					i = (n.useUtc ? we : be)("".concat(n.timeFormat).concat(n.useUtc ? " (UTC)" : ""));
				return "<strong>" + e.labelVal + " </strong>" + n.zDataLabel + (r ? " (<strong>" + Math.round((e.val - n.zColorScale.domain()[0]) / r * 100 * 100) / 100 + "%</strong>)" : "") + "<br><strong>From: </strong>" + i(e.timeRange[0]) + "<br><strong>To: </strong>" + i(e.timeRange[1])
			})),
			n.svg.call(n.segmentTooltip),
			r = function(t) {
				return ra(t, n.graph.node())
			},
			n.graph.on("mousedown", (function(t) {
				if (null == ea(window).on("mousemove.zoomRect")) {
					var e = r(t);
					if (!(e[0] < 0 || e[0] > n.graphW || e[1] < 0 || e[1] > n.graphH)) {
						n.disableHover = !0;
						var i = n.graph.append("rect").attr("class", "chart-zoom-selection");
						ea(window).on("mousemove.zoomRect", (function(t) {
							t.stopPropagation();
							var a = r(t),
								o = [Math.max(0, Math.min(n.graphW, a[0])), Math.max(0, Math.min(n.graphH, a[1]))];
							i.attr("x", Math.min(e[0], o[0])).attr("y", Math.min(e[1], o[1])).attr("width", Math.abs(o[0] - e[0])).attr("height", Math.abs(o[1] - e[1])),
							n.svg.dispatch("zoomScent", {
								detail: {
									zoomX: [e[0], o[0]].sort(c).map(n.xScale.invert),
									zoomY: [e[1], o[1]].sort(c).map((function(t) {
										return n.yScale.domain().indexOf(n.yScale.invert(t)) + (n.zoomY && n.zoomY[0] ? n.zoomY[0] : 0)
									}))
								}
							})
						})).on("mouseup.zoomRect", (function(t) {
							ea(window).on("mousemove.zoomRect", null).on("mouseup.zoomRect", null),
							ea("body").classed("stat-noselect", !1),
							i.remove(),
							n.disableHover = !1;
							var a = r(t),
								o = [Math.max(0, Math.min(n.graphW, a[0])), Math.max(0, Math.min(n.graphH, a[1]))];
							if (e[0] != o[0] || e[1] != o[1]) {
								var u = [e[0], o[0]].sort(c).map(n.xScale.invert),
									l = [e[1], o[1]].sort(c).map((function(t) {
										return n.yScale.domain().indexOf(n.yScale.invert(t)) + (n.zoomY && n.zoomY[0] ? n.zoomY[0] : 0)
									})),
									s = u[1] - u[0] > 1e3,
									f = l[0] != n.zoomY[0] || l[1] != n.zoomY[1];
								(s || f) && n.svg.dispatch("zoom", {
									detail: {
										zoomX: s ? u : null,
										zoomY: f ? l : null
									}
								})
							}
						}), !0),
						t.stopPropagation()
					}
				}
			})),
			n.resetBtn = n.svg.append("text").attr("class", "reset-zoom-btn").text("Reset Zoom").style("text-anchor", "end").on("mouseup", (function() {
				n.svg.dispatch("resetZoom")
			})).on("mouseover", (function() {
				ea(this).style("opacity", 1)
			})).on("mouseout", (function() {
				ea(this).style("opacity", .6)
			})),
			n.svg.on("zoom", (function(t) {
				var e = t.detail,
					r = e.zoomX,
					i = e.zoomY,
					a = null == e.redraw || e.redraw;
				(r || i) && (r && (n.zoomX = r), i && (n.zoomY = i), n.svg.dispatch("zoomScent", {
					detail: {
						zoomX: r,
						zoomY: i
					}
				}), a && (n._rerender(), n.onZoom && n.onZoom(n.zoomX, n.zoomY)))
			})),
			n.svg.on("resetZoom", (function() {
				var t = n.zoomX,
					e = n.zoomY || [null, null],
					r = n.enableOverview ? n.overviewArea.domainRange() : [k(n.flatData, (function(t) {
						return t.timeRange[0]
					})), S(n.flatData, (function(t) {
						return t.timeRange[1]
					}))],
					i = [null, null];
				(t[0] < r[0] || t[1] > r[1] || e[0] != i[0] || e[1] != r[1]) && (n.zoomX = [new Date(Math.min(t[0], r[0])), new Date(Math.max(t[1], r[1]))], n.zoomY = i, n.svg.dispatch("zoomScent", {
					detail: {
						zoomX: n.zoomX,
						zoomY: n.zoomY
					}
				}), n._rerender()),
				n.onZoom && n.onZoom(null, null)
			}))
		},
		update: function(n) {
			!function() {
				if (n.flatData = n.minSegmentDuration > 0 ? n.completeFlatData.filter((function(t) {
					return t.timeRange[1] - t.timeRange[0] >= n.minSegmentDuration
				})) : n.completeFlatData, null == n.zoomY || n.zoomY == [null, null]) {
					n.structData = n.completeStructData,
					n.nLines = 0;
					for (var t = 0, e = n.structData.length; t < e; t++)
						n.nLines += n.structData[t].lines.length;
					return
				}
				n.structData = [];
				var r = [null == n.zoomY[0] ? 0 : n.zoomY[0]];
				r.push(Math.max(0, (null == n.zoomY[1] ? n.totalNLines : n.zoomY[1] + 1) - r[0])),
				n.nLines = r[1];
				for (var i = function(t) {
						var e = n.completeStructData[t].lines;
						if (n.minSegmentDuration > 0) {
							if (!n.flatData.some((function(e) {
								return e.group == n.completeStructData[t].group
							})))
								return "continue";
							e = n.completeStructData[t].lines.filter((function(e) {
								return n.flatData.some((function(r) {
									return r.group == n.completeStructData[t].group && r.label == e
								}))
							}))
						}
						if (r[0] >= e.length)
							return r[0] -= e.length, "continue";
						var i = {
							group: n.completeStructData[t].group,
							lines: null
						};
						if (e.length - r[0] >= r[1])
							return i.lines = e.slice(r[0], r[1] + r[0]), n.structData.push(i), r[1] = 0, "break";
						r[0] > 0 ? (i.lines = e.slice(r[0]), r[0] = 0) : i.lines = e,
						n.structData.push(i),
						r[1] -= i.lines.length
					}, a = 0, o = n.completeStructData.length; a < o; a++) {
					var u = i(a);
					if ("continue" !== u && "break" === u)
						break
				}
				n.nLines -= r[1]
			}(),
			n.graphW = n.width - n.leftMargin - n.rightMargin,
			n.graphH = k([n.nLines * n.maxLineHeight, n.maxHeight - n.topMargin - n.bottomMargin]),
			n.height = n.graphH + n.topMargin + n.bottomMargin,
			n.svg.transition().duration(n.transDuration).attr("width", n.width).attr("height", n.height),
			n.graph.attr("transform", "translate(" + n.leftMargin + "," + n.topMargin + ")"),
			n.overviewArea && n.overviewArea.width(.8 * n.width).height(n.overviewHeight + n.overviewArea.margins().top + n.overviewArea.margins().bottom),
			n.zoomX[0] = n.zoomX[0] || k(n.flatData, (function(t) {
				return t.timeRange[0]
			})),
			n.zoomX[1] = n.zoomX[1] || S(n.flatData, (function(t) {
				return t.timeRange[1]
			})),
			n.xScale = (n.useUtc ? $r : jr)().domain(n.zoomX).range([0, n.graphW]).clamp(!0),
			n.overviewArea && n.overviewArea.scale(n.xScale.copy()).tickFormat(n.xTickFormat),
			function() {
				for (var t = [], e = function(e) {
						t = t.concat(n.structData[e].lines.map((function(t) {
							return n.structData[e].group + "+&+" + t
						})))
					}, r = 0, i = n.structData.length; r < i; r++)
					e(r);
				n.yScale.domain(t),
				n.yScale.range([n.graphH / t.length * .5, n.graphH * (1 - .5 / t.length)])
			}(),
			function() {
				n.grpScale.domain(n.structData.map((function(t) {
					return t.group
				})));
				var t = 0;
				n.grpScale.range(n.structData.map((function(e) {
					var r = (t + e.lines.length / 2) / n.nLines * n.graphH;
					return t += e.lines.length, r
				})))
			}(),
			function() {
				n.svg.select(".axises").attr("transform", "translate(" + n.leftMargin + "," + n.topMargin + ")");
				var e = Math.max(2, Math.min(12, Math.round(.012 * n.graphW)));
				n.xAxis.scale(n.xScale).ticks(e).tickFormat(n.xTickFormat),
				n.xGrid.scale(n.xScale).ticks(e).tickFormat(""),
				n.svg.select("g.x-axis").style("stroke-opacity", 0).style("fill-opacity", 0).attr("transform", "translate(0," + n.graphH + ")").transition().duration(n.transDuration).call(n.xAxis).style("stroke-opacity", 1).style("fill-opacity", 1),
				n.xGrid.tickSize(n.graphH),
				n.svg.select("g.x-grid").attr("transform", "translate(0," + n.graphH + ")").transition().duration(n.transDuration).call(n.xGrid),
				n.dateMarker && n.dateMarker >= n.xScale.domain()[0] && n.dateMarker <= n.xScale.domain()[1] ? n.dateMarkerLine.style("display", "block").transition().duration(n.transDuration).attr("x1", n.xScale(n.dateMarker) + n.leftMargin).attr("x2", n.xScale(n.dateMarker) + n.leftMargin).attr("y1", n.topMargin + 1).attr("y2", n.graphH + n.topMargin) : n.dateMarkerLine.style("display", "none");
				var r = Math.ceil(n.nLines * n.minLabelFont / Math.sqrt(2) / n.graphH / .6),
					i = n.yScale.domain().filter((function(t, n) {
						return !(n % r)
					})),
					a = Math.min(12, n.graphH / i.length * .6 * Math.sqrt(2)),
					o = Math.ceil(n.rightMargin / (a / Math.sqrt(2)));
				n.yAxis.tickValues(i),
				n.yAxis.tickFormat((function(t) {
					return l(t.split("+&+")[1], o)
				})),
				n.svg.select("g.y-axis").transition().duration(n.transDuration).attr("transform", "translate(" + n.graphW + ", 0)").style("font-size", a + "px").call(n.yAxis);
				var u = k(n.grpScale.range(), (function(t, e) {
					return e > 0 ? t - n.grpScale.range()[e - 1] : 2 * t
				}));
				a = Math.min(14, .6 * u * Math.sqrt(2)),
				o = Math.floor(n.leftMargin / (a / Math.sqrt(2))),
				n.grpAxis.tickFormat((function(t) {
					return l(t, o)
				})),
				n.svg.select("g.grp-axis").transition().duration(n.transDuration).style("font-size", a + "px").call(n.grpAxis),
				n.onLabelClick && n.svg.selectAll("g.y-axis,g.grp-axis").selectAll("text").style("cursor", "pointer").on("click", (function(e, r) {
					var i = r.split("+&+");
					n.onLabelClick.apply(n, t(i.reverse()))
				}));
				function l(t, n) {
					return t.length <= n ? t : t.substring(0, 2 * n / 3) + "..." + t.substring(t.length - n / 3, t.length)
				}
			}(),
			function() {
				var t = n.graph.selectAll("rect.series-group").data(n.structData, (function(t) {
					return t.group
				}));
				t.exit().transition().duration(n.transDuration).style("stroke-opacity", 0).style("fill-opacity", 0).remove();
				var e = t.enter().append("rect").attr("class", "series-group").attr("x", 0).attr("y", 0).attr("height", 0).style("fill", "url(#" + n.groupGradId + ")").on("mouseover", n.groupTooltip.show).on("mouseout", n.groupTooltip.hide);
				e.append("title").text("click-drag to zoom in"),
				(t = t.merge(e)).transition().duration(n.transDuration).attr("width", n.graphW).attr("height", (function(t) {
					return n.graphH * t.lines.length / n.nLines
				})).attr("y", (function(t) {
					return n.grpScale(t.group) - n.graphH * t.lines.length / n.nLines / 2
				}))
			}(),
			function(t) {
				t < 0 && (t = null);
				n.lineHeight = n.graphH / n.nLines * .8;
				var e = n.graph.selectAll("rect.series-segment").data(n.flatData.filter((function(e, r) {
					return (null == t || r < t) && n.grpScale.domain().indexOf(e.group) + 1 && e.timeRange[1] >= n.xScale.domain()[0] && e.timeRange[0] <= n.xScale.domain()[1] && n.yScale.domain().indexOf(e.group + "+&+" + e.label) + 1
				})), (function(t) {
					return t.group + t.label + t.timeRange[0]
				}));
				e.exit().transition().duration(n.transDuration).style("fill-opacity", 0).remove();
				var r = e.enter().append("rect").attr("class", "series-segment").attr("rx", 1).attr("ry", 1).attr("x", n.graphW / 2).attr("y", n.graphH / 2).attr("width", 0).attr("height", 0).style("fill", (function(t) {
					return n.zColorScale(t.val)
				})).style("fill-opacity", 0).on("mouseover.groupTooltip", n.groupTooltip.show).on("mouseout.groupTooltip", n.groupTooltip.hide).on("mouseover.lineTooltip", n.lineTooltip.show).on("mouseout.lineTooltip", n.lineTooltip.hide).on("mouseover.segmentTooltip", n.segmentTooltip.show).on("mouseout.segmentTooltip", n.segmentTooltip.hide);
				r.on("mouseover", (function() {
					if (!("disableHover" in n) || !n.disableHover) {
						_o()(this);
						var t = .4 * n.lineHeight;
						ea(this).transition().duration(70).attr("x", (function(e) {
							return n.xScale(e.timeRange[0]) - t / 2
						})).attr("width", (function(e) {
							return S([1, n.xScale(e.timeRange[1]) - n.xScale(e.timeRange[0])]) + t
						})).attr("y", (function(e) {
							return n.yScale(e.group + "+&+" + e.label) - (n.lineHeight + t) / 2
						})).attr("height", n.lineHeight + t).style("fill-opacity", 1)
					}
				})).on("mouseout", (function() {
					ea(this).transition().duration(250).attr("x", (function(t) {
						return n.xScale(t.timeRange[0])
					})).attr("width", (function(t) {
						return S([1, n.xScale(t.timeRange[1]) - n.xScale(t.timeRange[0])])
					})).attr("y", (function(t) {
						return n.yScale(t.group + "+&+" + t.label) - n.lineHeight / 2
					})).attr("height", n.lineHeight).style("fill-opacity", .8)
				})).on("click", (function(t, e) {
					n.onSegmentClick && n.onSegmentClick(e)
				})),
				e = e.merge(r),
				e.transition().duration(n.transDuration).attr("x", (function(t) {
					return n.xScale(t.timeRange[0])
				})).attr("width", (function(t) {
					return S([1, n.xScale(t.timeRange[1]) - n.xScale(t.timeRange[0])])
				})).attr("y", (function(t) {
					return n.yScale(t.group + "+&+" + t.label) - n.lineHeight / 2
				})).attr("height", n.lineHeight).style("fill", (function(t) {
					return n.zColorScale(t.val)
				})).style("fill-opacity", .8)
			}(),
			n.svg.select(".legendG").transition().duration(n.transDuration).attr("transform", "translate(".concat(n.leftMargin + .05 * n.graphW, ",2)")),
			n.colorLegend.width(Math.max(120, n.graphW / 3 * (n.zQualitative ? 2 : 1))).height(.6 * n.topMargin).scale(n.zColorScale).label(n.zScaleLabel),
			n.resetBtn.transition().duration(n.transDuration).attr("x", n.leftMargin + .99 * n.graphW).attr("y", .8 * n.topMargin),
			So().bbox({
				width: .4 * n.graphW,
				height: Math.min(13, .8 * n.topMargin)
			})(n.resetBtn.node())
		}
	})
}));
