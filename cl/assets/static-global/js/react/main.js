/******/ (function(modules) { // webpackBootstrap
/******/ 	// install a JSONP callback for chunk loading
/******/ 	function webpackJsonpCallback(data) {
/******/ 		var chunkIds = data[0];
/******/ 		var moreModules = data[1];
/******/ 		var executeModules = data[2];
/******/
/******/ 		// add "moreModules" to the modules object,
/******/ 		// then flag all "chunkIds" as loaded and fire callback
/******/ 		var moduleId, chunkId, i = 0, resolves = [];
/******/ 		for(;i < chunkIds.length; i++) {
/******/ 			chunkId = chunkIds[i];
/******/ 			if(Object.prototype.hasOwnProperty.call(installedChunks, chunkId) && installedChunks[chunkId]) {
/******/ 				resolves.push(installedChunks[chunkId][0]);
/******/ 			}
/******/ 			installedChunks[chunkId] = 0;
/******/ 		}
/******/ 		for(moduleId in moreModules) {
/******/ 			if(Object.prototype.hasOwnProperty.call(moreModules, moduleId)) {
/******/ 				modules[moduleId] = moreModules[moduleId];
/******/ 			}
/******/ 		}
/******/ 		if(parentJsonpFunction) parentJsonpFunction(data);
/******/
/******/ 		while(resolves.length) {
/******/ 			resolves.shift()();
/******/ 		}
/******/
/******/ 		// add entry modules from loaded chunk to deferred list
/******/ 		deferredModules.push.apply(deferredModules, executeModules || []);
/******/
/******/ 		// run deferred modules when all chunks ready
/******/ 		return checkDeferredModules();
/******/ 	};
/******/ 	function checkDeferredModules() {
/******/ 		var result;
/******/ 		for(var i = 0; i < deferredModules.length; i++) {
/******/ 			var deferredModule = deferredModules[i];
/******/ 			var fulfilled = true;
/******/ 			for(var j = 1; j < deferredModule.length; j++) {
/******/ 				var depId = deferredModule[j];
/******/ 				if(installedChunks[depId] !== 0) fulfilled = false;
/******/ 			}
/******/ 			if(fulfilled) {
/******/ 				deferredModules.splice(i--, 1);
/******/ 				result = __webpack_require__(__webpack_require__.s = deferredModule[0]);
/******/ 			}
/******/ 		}
/******/
/******/ 		return result;
/******/ 	}
/******/
/******/ 	// The module cache
/******/ 	var installedModules = {};
/******/
/******/ 	// object to store loaded and loading chunks
/******/ 	// undefined = chunk not loaded, null = chunk preloaded/prefetched
/******/ 	// Promise = chunk loading, 0 = chunk loaded
/******/ 	var installedChunks = {
/******/ 		"main": 0
/******/ 	};
/******/
/******/ 	var deferredModules = [];
/******/
/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {
/******/
/******/ 		// Check if module is in cache
/******/ 		if(installedModules[moduleId]) {
/******/ 			return installedModules[moduleId].exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = installedModules[moduleId] = {
/******/ 			i: moduleId,
/******/ 			l: false,
/******/ 			exports: {}
/******/ 		};
/******/
/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/
/******/ 		// Flag the module as loaded
/******/ 		module.l = true;
/******/
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/
/******/
/******/ 	// expose the modules object (__webpack_modules__)
/******/ 	__webpack_require__.m = modules;
/******/
/******/ 	// expose the module cache
/******/ 	__webpack_require__.c = installedModules;
/******/
/******/ 	// define getter function for harmony exports
/******/ 	__webpack_require__.d = function(exports, name, getter) {
/******/ 		if(!__webpack_require__.o(exports, name)) {
/******/ 			Object.defineProperty(exports, name, { enumerable: true, get: getter });
/******/ 		}
/******/ 	};
/******/
/******/ 	// define __esModule on exports
/******/ 	__webpack_require__.r = function(exports) {
/******/ 		if(typeof Symbol !== 'undefined' && Symbol.toStringTag) {
/******/ 			Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' });
/******/ 		}
/******/ 		Object.defineProperty(exports, '__esModule', { value: true });
/******/ 	};
/******/
/******/ 	// create a fake namespace object
/******/ 	// mode & 1: value is a module id, require it
/******/ 	// mode & 2: merge all properties of value into the ns
/******/ 	// mode & 4: return value when already ns object
/******/ 	// mode & 8|1: behave like require
/******/ 	__webpack_require__.t = function(value, mode) {
/******/ 		if(mode & 1) value = __webpack_require__(value);
/******/ 		if(mode & 8) return value;
/******/ 		if((mode & 4) && typeof value === 'object' && value && value.__esModule) return value;
/******/ 		var ns = Object.create(null);
/******/ 		__webpack_require__.r(ns);
/******/ 		Object.defineProperty(ns, 'default', { enumerable: true, value: value });
/******/ 		if(mode & 2 && typeof value != 'string') for(var key in value) __webpack_require__.d(ns, key, function(key) { return value[key]; }.bind(null, key));
/******/ 		return ns;
/******/ 	};
/******/
/******/ 	// getDefaultExport function for compatibility with non-harmony modules
/******/ 	__webpack_require__.n = function(module) {
/******/ 		var getter = module && module.__esModule ?
/******/ 			function getDefault() { return module['default']; } :
/******/ 			function getModuleExports() { return module; };
/******/ 		__webpack_require__.d(getter, 'a', getter);
/******/ 		return getter;
/******/ 	};
/******/
/******/ 	// Object.prototype.hasOwnProperty.call
/******/ 	__webpack_require__.o = function(object, property) { return Object.prototype.hasOwnProperty.call(object, property); };
/******/
/******/ 	// __webpack_public_path__
/******/ 	__webpack_require__.p = "http://localhost:3000/assets/bundles/";
/******/
/******/ 	var jsonpArray = window["webpackJsonp"] = window["webpackJsonp"] || [];
/******/ 	var oldJsonpFunction = jsonpArray.push.bind(jsonpArray);
/******/ 	jsonpArray.push = webpackJsonpCallback;
/******/ 	jsonpArray = jsonpArray.slice();
/******/ 	for(var i = 0; i < jsonpArray.length; i++) webpackJsonpCallback(jsonpArray[i]);
/******/ 	var parentJsonpFunction = oldJsonpFunction;
/******/
/******/
/******/ 	// add entry module to deferred list
/******/ 	deferredModules.push([0,"vendor"]);
/******/ 	// run deferred modules when ready
/******/ 	return checkDeferredModules();
/******/ })
/************************************************************************/
/******/ ({

/***/ "./assets/react/ListItem.tsx":
/*!***********************************!*\
  !*** ./assets/react/ListItem.tsx ***!
  \***********************************/
/*! exports provided: ListItem */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "ListItem", function() { return ListItem; });
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_0__);

var ListItem = function ListItem(_ref) {
  var id = _ref.id,
      name = _ref.name,
      assocId = _ref.assocId,
      isSelected = _ref.isSelected,
      user = _ref.user;
  var isCreateItem = name.startsWith('Create Tag: ');
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("a", {
    className: "list-group-item cursor"
  }, isCreateItem ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("p", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("strong", null, name)) : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("div", {
    className: "form-check form-check-inline"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("input", {
    type: "checkbox",
    id: assocId === null || assocId === void 0 ? void 0 : assocId.toString(),
    value: name,
    checked: isSelected,
    onChange: function onChange(ev) {
      return ev.preventDefault();
    },
    style: {
      marginRight: '1rem'
    },
    className: "form-check position-static ".concat(isSelected ? 'checked' : ''),
    "data-tagid": id
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("label", {
    className: "form-check-label"
  }, name), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("span", {
    className: "float-right gray"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement("i", {
    className: "fa fa-external-link cursor",
    onClick: function onClick() {
      return window.location.href = "/tags/".concat(user, "/").concat(name, "/");
    },
    title: "View this tag"
  }))));
};

/***/ }),

/***/ "./assets/react/TagList.tsx":
/*!**********************************!*\
  !*** ./assets/react/TagList.tsx ***!
  \**********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/regenerator */ "./node_modules/@babel/runtime/regenerator/index.js");
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/helpers/asyncToGenerator */ "./node_modules/@babel/runtime/helpers/asyncToGenerator.js");
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var react_query__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react-query */ "./node_modules/react-query/dist/react-query.mjs");
/* harmony import */ var _TagListInner__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./TagListInner */ "./assets/react/TagListInner.tsx");
/* harmony import */ var _fetch__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./_fetch */ "./assets/react/_fetch.ts");








var TagList = function TagList(_ref) {
  var userId = _ref.userId,
      userName = _ref.userName,
      isPageOwner = _ref.isPageOwner;

  var _React$useState = react__WEBPACK_IMPORTED_MODULE_3___default.a.useState(1),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_2___default()(_React$useState, 2),
      page = _React$useState2[0],
      setPage = _React$useState2[1];

  var getTags = react__WEBPACK_IMPORTED_MODULE_3___default.a.useCallback( /*#__PURE__*/function () {
    var _ref2 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_1___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default.a.mark(function _callee(key) {
      var page,
          _args = arguments;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default.a.wrap(function _callee$(_context) {
        while (1) {
          switch (_context.prev = _context.next) {
            case 0:
              page = _args.length > 1 && _args[1] !== undefined ? _args[1] : 1;
              _context.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_6__["appFetch"])("/api/rest/v3/tags/?user=".concat(userId, "&page=").concat(page, "&page_size=10&order_by=name"));

            case 3:
              return _context.abrupt("return", _context.sent);

            case 4:
            case "end":
              return _context.stop();
          }
        }
      }, _callee);
    }));

    return function (_x) {
      return _ref2.apply(this, arguments);
    };
  }(), []);

  var _usePaginatedQuery = Object(react_query__WEBPACK_IMPORTED_MODULE_4__["usePaginatedQuery"])( // this has been deprecated...
  ['tags', page], getTags),
      isLoading = _usePaginatedQuery.isLoading,
      isError = _usePaginatedQuery.isError,
      error = _usePaginatedQuery.error,
      resolvedData = _usePaginatedQuery.resolvedData,
      latestData = _usePaginatedQuery.latestData,
      isFetching = _usePaginatedQuery.isFetching;

  if (latestData == undefined) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Loading...");
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("h1", null, "Tags for: ", userName), isLoading ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Loading...") : isError ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Error: ", error.message, " ") : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(_TagListInner__WEBPACK_IMPORTED_MODULE_5__["default"], {
    data: latestData.results,
    isPageOwner: isPageOwner,
    userName: userName
  }), page === 1 && latestData && !latestData.next ? null : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "well v-offset-above-3 hidden-print"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "row"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "col-xs-2 col-sm-3"
  }, page > 1 ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "text-left"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("a", {
    onClick: function onClick() {
      return setPage(function (old) {
        return Math.max(old - 1, 0);
      });
    },
    className: "btn btn-default",
    rel: "prev"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("i", {
    className: "fa fa-caret-left no-underline"
  }), "\xA0", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("span", {
    className: "hidden-xs hidden-sm"
  }, "Previous"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("span", {
    className: "hidden-xs hidden-md hidden-lg"
  }, "Prev."))) : null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "col-xs-8 col-sm-6"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "text-center large"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("span", {
    className: "hidden-xs"
  }, isFetching ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_3___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("i", {
    className: "fa fa-spinner fa-pulse gray"
  }), "\xA0Loading...") : 'Page ' + page))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "col-xs-2 col-sm-3"
  }, latestData && latestData.next ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", {
    className: "text-right"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("a", {
    onClick: function onClick() {
      return (// Here, we use `latestData` so the Next Page
        // button isn't relying on potentially old data
        setPage(function (old) {
          return !latestData || !latestData.next ? old : old + 1;
        })
      );
    },
    rel: "next",
    className: "btn btn-default"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("span", {
    className: "hidden-xs"
  }, "Next"), "\xA0", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("i", {
    className: "fa fa-caret-right no-underline"
  }))) : null))), isFetching ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("span", null, " Fetching...") : null, ' ');
};

/* harmony default export */ __webpack_exports__["default"] = (TagList);

/***/ }),

/***/ "./assets/react/TagListInner.tsx":
/*!***************************************!*\
  !*** ./assets/react/TagListInner.tsx ***!
  \***************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var date_fns__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! date-fns */ "./node_modules/date-fns/esm/index.js");
/* harmony import */ var react_bootstrap__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! react-bootstrap */ "./node_modules/react-bootstrap/es/index.js");
/* harmony import */ var react_input_switch__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react-input-switch */ "./node_modules/react-input-switch/dist/index.esm.js");
/* harmony import */ var _useTags__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./_useTags */ "./assets/react/_useTags.ts");







var Toggle = function Toggle(_ref) {
  var state = _ref.state,
      name = _ref.name,
      id = _ref.id;

  var _updateTags = Object(_useTags__WEBPACK_IMPORTED_MODULE_5__["updateTags"])(),
      modifyTags = _updateTags.modifyTags,
      deleteTags = _updateTags.deleteTags;

  var _useState = Object(react__WEBPACK_IMPORTED_MODULE_1__["useState"])(+state),
      _useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_useState, 2),
      value = _useState2[0],
      setValue = _useState2[1];

  function trigger_state_change(key) {
    setValue(key);
    modifyTags({
      published: !!key,
      name: name,
      id: id
    });
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_input_switch__WEBPACK_IMPORTED_MODULE_4__["default"], {
    className: 'toggle',
    value: value,
    onChange: trigger_state_change
  });
};

var TagListInner = function TagListInner(_ref2) {
  var data = _ref2.data,
      isPageOwner = _ref2.isPageOwner,
      userName = _ref2.userName;

  var _updateTags2 = Object(_useTags__WEBPACK_IMPORTED_MODULE_5__["updateTags"])(),
      modifyTags = _updateTags2.modifyTags,
      deleteTags = _updateTags2.deleteTags;

  var delete_tag = function delete_tag(e, tag_id) {
    if (window.confirm('Are you sure you wish to delete this item?')) {
      deleteTags(tag_id);
      window.location.reload(false);
    }
  };

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    className: "table-responsive"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("table", {
    className: "table settings-table tablesorter-bootstrap"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("thead", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tr", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Name"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Created"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Views"), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Public"), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Delete"))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tbody", null, data.map(function (tag) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tr", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        "cursor": "pointer"
      },
      onClick: function onClick() {
        return window.location.href = "/tags/".concat(userName, "/").concat(tag.name, "/");
      }
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("a", {
      href: "/tags/".concat(userName, "/").concat(tag.name, "/"),
      className: "black-link"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
      className: "tag"
    }, tag.name))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        "cursor": "pointer"
      },
      onClick: function onClick() {
        return window.location.href = "/tags/".concat(userName, "/").concat(tag.name, "/");
      }
    }, Object(date_fns__WEBPACK_IMPORTED_MODULE_2__["format"])(Object(date_fns__WEBPACK_IMPORTED_MODULE_2__["parseISO"])(tag.date_created || ""), 'MMM d, yyyy')), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        "cursor": "pointer"
      },
      onClick: function onClick() {
        return window.location.href = "/tags/".concat(userName, "/").concat(tag.name, "/");
      }
    }, tag.view_count), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_1___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(Toggle, {
      id: tag.id,
      name: tag.name,
      state: tag.published
    })), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_3__["Button"], {
      id: "dlt_".concat(tag.id),
      onClick: function onClick(event) {
        return delete_tag(event, Number("".concat(tag.id)));
      },
      className: "fa fa-trash btn-sm inline"
    }, " Delete"))));
  }))));
};

/* harmony default export */ __webpack_exports__["default"] = (TagListInner);

/***/ }),

/***/ "./assets/react/TagPage.tsx":
/*!**********************************!*\
  !*** ./assets/react/TagPage.tsx ***!
  \**********************************/
/*! exports provided: TagMarkdown */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "TagMarkdown", function() { return TagMarkdown; });
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var react_showdown__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! react-showdown */ "./node_modules/react-showdown/dist/react-showdown.esm.js");
/* harmony import */ var react_simplemde_editor__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! react-simplemde-editor */ "./node_modules/react-simplemde-editor/lib/index.js");
/* harmony import */ var react_simplemde_editor__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(react_simplemde_editor__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var _useTags__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./_useTags */ "./assets/react/_useTags.ts");
/* harmony import */ var react_bootstrap__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! react-bootstrap */ "./node_modules/react-bootstrap/es/index.js");
/* harmony import */ var easymde_dist_easymde_min_css__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! easymde/dist/easymde.min.css */ "./node_modules/easymde/dist/easymde.min.css");
/* harmony import */ var _tag_page_css__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./tag-page.css */ "./assets/react/tag-page.css");
/* harmony import */ var react_input_switch__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! react-input-switch */ "./node_modules/react-input-switch/dist/index.esm.js");









var markdown_options = {
  autoRefresh: true,
  uploadImage: false,
  placeholder: "Add your descriptions here...",
  maxHeight: "400px",
  minHeight: "400px",
  sideBySideFullscreen: false,
  status: false,
  toolbar: ['bold', 'italic', 'heading', '|', 'quote', 'code', 'horizontal-rule', 'unordered-list', 'ordered-list', 'table', 'link', '|', 'side-by-side', {
    name: 'guide',
    action: function action() {
      var win = window.open('https://www.courtlistener.com/help/markdown/', '_blank');

      if (win) {
        win.focus();
      }
    },
    className: 'fa fa-info-circle',
    title: 'Markdown Syntax'
  }]
};

var PageTop = function PageTop(data) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_1___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    className: "row"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    className: "col-md-2"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("h1", {
    className: "clearfix"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
    className: "tag"
  }, data.name)))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("p", null, "Created by", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
    className: "alt"
  }, " ", data.user), " on", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
    className: "alt"
  }, " ", data.dateCreatedDate), " with ", data.viewCount));
};

var TagOptions = function TagOptions(data) {
  var _updateTags = Object(_useTags__WEBPACK_IMPORTED_MODULE_4__["updateTags"])(),
      modifyTags = _updateTags.modifyTags,
      deleteTags = _updateTags.deleteTags;

  var _useState = Object(react__WEBPACK_IMPORTED_MODULE_1__["useState"])(data.published == 'True'),
      _useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_useState, 2),
      isPublic = _useState2[0],
      setPublic = _useState2[1];

  var delete_tag = function delete_tag(tag_id) {
    if (window.confirm('Are you sure you wish to delete this item???')) {
      deleteTags(tag_id); // Relocate to the previous page on delete

      var url = window.location.href.slice(0, -1);
      window.location.href = url.substr(0, url.lastIndexOf('/') + 1);
    }
  };

  function toggle_menu(e, published, name, id) {
    modifyTags({
      published: !published,
      name: name,
      id: id
    });
    setPublic(!published);
    e.parent().toggleClass('open');
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    id: "tag-settings-parent",
    className: "float-right v-offset-above-1"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["ButtonToolbar"], null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["DropdownButton"], {
    pullRight: true,
    className: "fa fa-gear gray",
    bsSize: "large",
    noCaret: true,
    title: "",
    id: "tag-settings"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["MenuItem"], {
    onClick: function onClick(event) {
      return toggle_menu(event, isPublic, "".concat(data.name), Number("".concat(data.id)));
    }
  }, "Is Publicly Available\xA0", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_input_switch__WEBPACK_IMPORTED_MODULE_8__["default"], {
    className: 'toggle',
    value: +isPublic
  })), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["MenuItem"], {
    divider: true
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["MenuItem"], {
    checked: true,
    onClick: function onClick(_) {
      return delete_tag(Number("".concat(data.id)));
    },
    eventKey: "4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("i", {
    className: "fa fa-trash gray"
  }), "\xA0Delete")))));
};

var TagMarkdown = function TagMarkdown(data) {
  var _updateTags2 = Object(_useTags__WEBPACK_IMPORTED_MODULE_4__["updateTags"])(),
      modifyTags = _updateTags2.modifyTags,
      deleteTags = _updateTags2.deleteTags;

  var _useState3 = Object(react__WEBPACK_IMPORTED_MODULE_1__["useState"])(data.description),
      _useState4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_useState3, 2),
      text = _useState4[0],
      setText = _useState4[1];

  var _useState5 = Object(react__WEBPACK_IMPORTED_MODULE_1__["useState"])('write'),
      _useState6 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_useState5, 2),
      key = _useState6[0],
      setKey = _useState6[1];

  var _useState7 = Object(react__WEBPACK_IMPORTED_MODULE_1__["useState"])(true),
      _useState8 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_useState7, 2),
      disabled = _useState8[0],
      setDisabled = _useState8[1];

  function save_on_select(k) {
    if (k !== key) {
      if (k == "write") {
        var tag = {
          description: text,
          name: data.name,
          id: data.id
        };
        modifyTags(tag).then(function (_) {
          setDisabled(true);
        });
      }
    }

    setKey(k);
  }

  function save_button() {
    var tag = {
      description: text,
      name: data.name,
      id: data.id
    };
    modifyTags(tag).then(function (_) {
      setDisabled(true);
    });
  }

  function update(markdown) {
    setText(markdown);
    setDisabled(false);
  }

  if (data.pageOwner == "False") {
    if (text == "") {
      return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(PageTop, data));
    }

    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(PageTop, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
      id: "markdown_viewer",
      className: "col-12 view-only"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_showdown__WEBPACK_IMPORTED_MODULE_2__["default"], {
      markdown: text || "",
      flavor: "github",
      options: {
        tables: true,
        emoji: true,
        simpleLineBreaks: true
      }
    })));
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(TagOptions, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(PageTop, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["TabContainer"], {
    id: "tab-tabs",
    defaultActiveKey: "first"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["Tabs"], {
    id: "controlled-tab-example",
    activeKey: key,
    onSelect: save_on_select
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["Tab"], {
    eventKey: "write",
    title: "Notes"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    id: "markdown_viewer",
    className: "col-12"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_showdown__WEBPACK_IMPORTED_MODULE_2__["default"], {
    markdown: text || "",
    flavor: "github",
    options: {
      tables: true,
      emoji: true,
      simpleLineBreaks: true
    }
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["Tab"], {
    eventKey: "preview",
    title: "Edit"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_simplemde_editor__WEBPACK_IMPORTED_MODULE_3___default.a, {
    options: markdown_options,
    value: text,
    onChange: update
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
    id: "save_span",
    style: {
      "float": "right"
    }
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_5__["Button"], {
    disabled: disabled,
    id: 'save_button',
    onClick: save_button,
    className: "fa fa-save whitesmoke"
  }, " Save"))))));
};



/***/ }),

/***/ "./assets/react/TagSelect.tsx":
/*!************************************!*\
  !*** ./assets/react/TagSelect.tsx ***!
  \************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/extends */ "./node_modules/@babel/runtime/helpers/extends.js");
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/helpers/defineProperty */ "./node_modules/@babel/runtime/helpers/defineProperty.js");
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/helpers/toConsumableArray */ "./node_modules/@babel/runtime/helpers/toConsumableArray.js");
/* harmony import */ var _babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var react_virtual__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! react-virtual */ "./node_modules/react-virtual/dist/react-virtual.mjs");
/* harmony import */ var downshift__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! downshift */ "./node_modules/downshift/dist/downshift.esm.js");
/* harmony import */ var _ListItem__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./ListItem */ "./assets/react/ListItem.tsx");
/* harmony import */ var _useTags__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! ./_useTags */ "./assets/react/_useTags.ts");





function ownKeys(object, enumerableOnly) { var keys = Object.keys(object); if (Object.getOwnPropertySymbols) { var symbols = Object.getOwnPropertySymbols(object); if (enumerableOnly) symbols = symbols.filter(function (sym) { return Object.getOwnPropertyDescriptor(object, sym).enumerable; }); keys.push.apply(keys, symbols); } return keys; }

function _objectSpread(target) { for (var i = 1; i < arguments.length; i++) { var source = arguments[i] != null ? arguments[i] : {}; if (i % 2) { ownKeys(Object(source), true).forEach(function (key) { _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default()(target, key, source[key]); }); } else if (Object.getOwnPropertyDescriptors) { Object.defineProperties(target, Object.getOwnPropertyDescriptors(source)); } else { ownKeys(Object(source)).forEach(function (key) { Object.defineProperty(target, key, Object.getOwnPropertyDescriptor(source, key)); }); } } return target; }







var TagSelect = function TagSelect(_ref) {
  var userId = _ref.userId,
      userName = _ref.userName,
      editUrl = _ref.editUrl,
      docket = _ref.docket;

  var _React$useState = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState(null),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState, 2),
      validationError = _React$useState2[0],
      setValidationError = _React$useState2[1];

  var _useTags = Object(_useTags__WEBPACK_IMPORTED_MODULE_8__["useTags"])({
    docket: docket,
    enabled: !!docket && userName,
    userId: userId
  }),
      _useTags$infiniteQuer = _useTags.infiniteQueryState,
      status = _useTags$infiniteQuer.status,
      canFetchMore = _useTags$infiniteQuer.canFetchMore,
      isFetching = _useTags$infiniteQuer.isFetching,
      isFetchingMore = _useTags$infiniteQuer.isFetchingMore,
      fetchMore = _useTags$infiniteQuer.fetchMore,
      textVal = _useTags.textVal,
      setTextVal = _useTags.setTextVal,
      tags = _useTags.tags,
      associations = _useTags.associations,
      addNewTag = _useTags.addNewTag,
      addNewAssociation = _useTags.addNewAssociation,
      deleteAssociation = _useTags.deleteAssociation;

  var parentRef = react__WEBPACK_IMPORTED_MODULE_4___default.a.useRef(null);
  var rowVirtualizer = Object(react_virtual__WEBPACK_IMPORTED_MODULE_5__["useVirtual"])({
    size: canFetchMore ? tags.length + 1 : tags.length,
    parentRef: parentRef,
    estimateSize: react__WEBPACK_IMPORTED_MODULE_4___default.a.useCallback(function () {
      return 40;
    }, [])
  }); // fetchmore if we are at the bottom of the list

  react__WEBPACK_IMPORTED_MODULE_4___default.a.useEffect(function () {
    var _reverse = _babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_2___default()(rowVirtualizer.virtualItems).reverse(),
        _reverse2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_reverse, 1),
        lastItem = _reverse2[0];

    if (!lastItem) return;

    if (lastItem.index === rowVirtualizer.virtualItems.length - 1 && canFetchMore && !isFetchingMore) {
      console.log('fetching more');
      fetchMore();
    }
  }, [canFetchMore, fetchMore, tags.length, isFetchingMore, rowVirtualizer.virtualItems]);

  var _useCombobox = Object(downshift__WEBPACK_IMPORTED_MODULE_6__["useCombobox"])({
    inputValue: textVal,
    itemToString: function itemToString(item) {
      return item ? item.name : '';
    },
    // set to none to select multiple
    selectedItem: null,
    items: tags,
    scrollIntoView: function scrollIntoView() {},
    stateReducer: function stateReducer(state, actionAndChanges) {
      var changes = actionAndChanges.changes,
          type = actionAndChanges.type;

      switch (type) {
        case downshift__WEBPACK_IMPORTED_MODULE_6__["useCombobox"].stateChangeTypes.InputKeyDownEnter:
        case downshift__WEBPACK_IMPORTED_MODULE_6__["useCombobox"].stateChangeTypes.ItemClick:
          return _objectSpread(_objectSpread({}, changes), {}, {
            isOpen: true,
            // keep menu open after selection.
            highlightedIndex: state.highlightedIndex,
            inputValue: ''
          });

        default:
          return changes;
      }
    },
    onSelectedItemChange: function onSelectedItemChange(_ref2) {
      var selectedItem = _ref2.selectedItem;
      if (!selectedItem) return;
      var isCreateItemOption = selectedItem.name.startsWith('Create Tag:');

      if (isCreateItemOption) {
        var validInput = textVal.match(/^[a-z0-9-]*$/);

        if (!validInput) {
          return setValidationError("Only lowercase letters, numbers, and '-' allowed");
        }

        return addNewTag({
          name: selectedItem.name.replace('Create Tag: ', '')
        });
      }

      var isAlreadySelected = !associations ? false : !!associations.find(function (a) {
        return a.tag === selectedItem.id;
      });

      if (isAlreadySelected) {
        console.log("Removing ".concat(selectedItem.name, " from tags for docket ").concat(docket));
        deleteAssociation({
          assocId: selectedItem.assocId
        });
      } else {
        console.log("Adding ".concat(selectedItem.name, " to tags for docket ").concat(docket));
        addNewAssociation({
          tag: parseInt(selectedItem.id, 10)
        });
      }
    },
    onHighlightedIndexChange: function onHighlightedIndexChange(_ref3) {
      var highlightedIndex = _ref3.highlightedIndex;

      if (highlightedIndex && highlightedIndex >= 0) {
        rowVirtualizer.scrollToIndex(highlightedIndex);
      }
    }
  }),
      isOpen = _useCombobox.isOpen,
      getToggleButtonProps = _useCombobox.getToggleButtonProps,
      getLabelProps = _useCombobox.getLabelProps,
      getMenuProps = _useCombobox.getMenuProps,
      getInputProps = _useCombobox.getInputProps,
      getComboboxProps = _useCombobox.getComboboxProps,
      highlightedIndex = _useCombobox.highlightedIndex,
      getItemProps = _useCombobox.getItemProps; // manually type nativeEvent as any
  // https://github.com/downshift-js/downshift/issues/734


  var disableDownshiftMenuToggle = function disableDownshiftMenuToggle(_ref4) {
    var nativeEvent = _ref4.nativeEvent;
    return nativeEvent.preventDownshiftDefault = true;
  };

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("button", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, getToggleButtonProps({
    onClick: function onClick(event) {
      // Anonymous user
      if (!userName) {
        disableDownshiftMenuToggle(event);
      }
    },
    onKeyDown: function onKeyDown(event) {
      if (!userName) {
        disableDownshiftMenuToggle(event);
      }
    }
  }), {
    "aria-label": "toggle tag menu",
    className: !userName ? 'btn btn-success logged-out-modal-trigger' : 'btn btn-success'
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-tags"
  }), "\xA0Tags ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", {
    className: "caret"
  })), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "list-group",
    style: {
      marginTop: '2px',
      border: isOpen ? '1px solid grey' : 'none',
      zIndex: isOpen ? 10 : 0,
      minWidth: '300px',
      maxWidth: '500px',
      position: 'absolute'
    }
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({
    type: "button",
    className: "list-group-item",
    style: {
      display: isOpen ? 'block' : 'none'
    }
  }, getLabelProps()), "Apply tags to this item"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({
    type: "button",
    style: {
      padding: '1em',
      display: isOpen ? 'block' : 'none'
    }
  }, getComboboxProps(), {
    className: "list-group-item"
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("input", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, getInputProps({
    onBlur: function onBlur(e) {
      return setValidationError(null);
    },
    onChange: function onChange(e) {
      return setTextVal(e.target.value);
    }
  }), {
    className: "form-control ".concat(validationError && 'is-invalid'),
    placeholder: "Search tags\u2026"
  })), validationError && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    style: {
      padding: '1px'
    },
    className: "invalid-feedback"
  }, validationError)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    style: {
      overflowY: isOpen ? 'auto' : 'hidden',
      maxHeight: '500px'
    }
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, getMenuProps({
    ref: parentRef
  }), {
    style: {
      height: "".concat(rowVirtualizer.totalSize, "px"),
      width: '100%',
      position: 'relative'
    }
  }), isOpen && rowVirtualizer.virtualItems.map(function (virtualRow, index) {
    var isLoaderRow = virtualRow.index > tags.length - 1;
    var tag = tags[virtualRow.index];
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
      key: virtualRow.index,
      style: {
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: "".concat(virtualRow.size, "px"),
        transform: "translateY(".concat(virtualRow.start, "px)")
      }
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({
      key: tag ? tag.name : 'loading row'
    }, getItemProps({
      item: tag,
      index: virtualRow.index
    }), {
      style: {
        backgroundColor: highlightedIndex === virtualRow.index ? '#bde4ff' : ''
      }
    }), isLoaderRow ? canFetchMore ? 'Loading more...' : 'Nothing more to load' : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement(_ListItem__WEBPACK_IMPORTED_MODULE_7__["ListItem"], _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({
      isSelected: !!associations.find(function (a) {
        return a.tag === tag.id;
      }),
      key: virtualRow.index,
      user: userName
    }, tag))));
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    style: {
      display: isOpen ? 'block' : 'none'
    },
    className: "list-group-item",
    href: editUrl
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-pencil",
    style: {
      marginRight: '1em'
    }
  }), "Edit Tags")));
};

/* harmony default export */ __webpack_exports__["default"] = (TagSelect);

/***/ }),

/***/ "./assets/react/_fetch.ts":
/*!********************************!*\
  !*** ./assets/react/_fetch.ts ***!
  \********************************/
/*! exports provided: appFetch */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "appFetch", function() { return appFetch; });
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/regenerator */ "./node_modules/@babel/runtime/regenerator/index.js");
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/helpers/defineProperty */ "./node_modules/@babel/runtime/helpers/defineProperty.js");
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/helpers/asyncToGenerator */ "./node_modules/@babel/runtime/helpers/asyncToGenerator.js");
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var js_cookie__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! js-cookie */ "./node_modules/js-cookie/src/js.cookie.js");
/* harmony import */ var js_cookie__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(js_cookie__WEBPACK_IMPORTED_MODULE_3__);




function ownKeys(object, enumerableOnly) { var keys = Object.keys(object); if (Object.getOwnPropertySymbols) { var symbols = Object.getOwnPropertySymbols(object); if (enumerableOnly) symbols = symbols.filter(function (sym) { return Object.getOwnPropertyDescriptor(object, sym).enumerable; }); keys.push.apply(keys, symbols); } return keys; }

function _objectSpread(target) { for (var i = 1; i < arguments.length; i++) { var source = arguments[i] != null ? arguments[i] : {}; if (i % 2) { ownKeys(Object(source), true).forEach(function (key) { _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default()(target, key, source[key]); }); } else if (Object.getOwnPropertyDescriptors) { Object.defineProperties(target, Object.getOwnPropertyDescriptors(source)); } else { ownKeys(Object(source)).forEach(function (key) { Object.defineProperty(target, key, Object.getOwnPropertyDescriptor(source, key)); }); } } return target; }


function appFetch(_x, _x2) {
  return _appFetch.apply(this, arguments);
}

function _appFetch() {
  _appFetch = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default.a.mark(function _callee(url, options) {
    var csrfTokenHeader, mergedOptions;
    return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_0___default.a.wrap(function _callee$(_context) {
      while (1) {
        switch (_context.prev = _context.next) {
          case 0:
            csrfTokenHeader = {
              'Content-Type': 'application/json',
              'X-CSRFToken': js_cookie__WEBPACK_IMPORTED_MODULE_3___default.a.get('csrftoken')
            };
            mergedOptions = {
              method: (options === null || options === void 0 ? void 0 : options.method) || 'GET',
              headers: (options === null || options === void 0 ? void 0 : options.headers) ? _objectSpread(_objectSpread({}, csrfTokenHeader), options.headers) : csrfTokenHeader
            };

            if (options === null || options === void 0 ? void 0 : options.body) {
              mergedOptions.body = JSON.stringify(options.body);
            }

            return _context.abrupt("return", fetch(url, mergedOptions).then(function (response) {
              if (!response.ok) {
                throw new Error(response.statusText);
              }

              if ((options === null || options === void 0 ? void 0 : options.method) === 'DELETE') return new Promise(function (resolve) {
                return resolve(true);
              });
              return response.json();
            }));

          case 4:
          case "end":
            return _context.stop();
        }
      }
    }, _callee);
  }));
  return _appFetch.apply(this, arguments);
}

/***/ }),

/***/ "./assets/react/_useTags.ts":
/*!**********************************!*\
  !*** ./assets/react/_useTags.ts ***!
  \**********************************/
/*! exports provided: useTags, updateTags */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "useTags", function() { return useTags; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "updateTags", function() { return updateTags; });
/* harmony import */ var _babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/toConsumableArray */ "./node_modules/@babel/runtime/helpers/toConsumableArray.js");
/* harmony import */ var _babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/helpers/defineProperty */ "./node_modules/@babel/runtime/helpers/defineProperty.js");
/* harmony import */ var _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/regenerator */ "./node_modules/@babel/runtime/regenerator/index.js");
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @babel/runtime/helpers/asyncToGenerator */ "./node_modules/@babel/runtime/helpers/asyncToGenerator.js");
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_5___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_5__);
/* harmony import */ var react_query__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! react-query */ "./node_modules/react-query/dist/react-query.mjs");
/* harmony import */ var _fetch__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./_fetch */ "./assets/react/_fetch.ts");






function ownKeys(object, enumerableOnly) { var keys = Object.keys(object); if (Object.getOwnPropertySymbols) { var symbols = Object.getOwnPropertySymbols(object); if (enumerableOnly) symbols = symbols.filter(function (sym) { return Object.getOwnPropertyDescriptor(object, sym).enumerable; }); keys.push.apply(keys, symbols); } return keys; }

function _objectSpread(target) { for (var i = 1; i < arguments.length; i++) { var source = arguments[i] != null ? arguments[i] : {}; if (i % 2) { ownKeys(Object(source), true).forEach(function (key) { _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default()(target, key, source[key]); }); } else if (Object.getOwnPropertyDescriptors) { Object.defineProperties(target, Object.getOwnPropertyDescriptors(source)); } else { ownKeys(Object(source)).forEach(function (key) { Object.defineProperty(target, key, Object.getOwnPropertyDescriptor(source, key)); }); } } return target; }




var useTags = function useTags(_ref) {
  var docket = _ref.docket,
      enabled = _ref.enabled,
      userId = _ref.userId;

  var _React$useState = react__WEBPACK_IMPORTED_MODULE_5___default.a.useState(''),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_React$useState, 2),
      textVal = _React$useState2[0],
      setTextVal = _React$useState2[1];

  var getTags = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref2 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee(key) {
      var page,
          _args = arguments;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee$(_context) {
        while (1) {
          switch (_context.prev = _context.next) {
            case 0:
              page = _args.length > 1 && _args[1] !== undefined ? _args[1] : 1;
              _context.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])("/api/rest/v3/tags/?user=".concat(userId, "&page=").concat(page));

            case 3:
              return _context.abrupt("return", _context.sent);

            case 4:
            case "end":
              return _context.stop();
          }
        }
      }, _callee);
    }));

    return function (_x) {
      return _ref2.apply(this, arguments);
    };
  }(), []);
  var getAssociations = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref3 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee2(key) {
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee2$(_context2) {
        while (1) {
          switch (_context2.prev = _context2.next) {
            case 0:
              _context2.next = 2;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])("/api/rest/v3/docket-tags/?docket=".concat(docket));

            case 2:
              return _context2.abrupt("return", _context2.sent);

            case 3:
            case "end":
              return _context2.stop();
          }
        }
      }, _callee2);
    }));

    return function (_x2) {
      return _ref3.apply(this, arguments);
    };
  }(), [docket]);
  var postTag = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref5 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee3(_ref4) {
      var name;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee3$(_context3) {
        while (1) {
          switch (_context3.prev = _context3.next) {
            case 0:
              name = _ref4.name;
              _context3.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])('/api/rest/v3/tags/', {
                method: 'POST',
                body: {
                  name: name
                }
              });

            case 3:
              return _context3.abrupt("return", _context3.sent);

            case 4:
            case "end":
              return _context3.stop();
          }
        }
      }, _callee3);
    }));

    return function (_x3) {
      return _ref5.apply(this, arguments);
    };
  }(), []);
  var postAssoc = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref7 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee4(_ref6) {
      var tag;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee4$(_context4) {
        while (1) {
          switch (_context4.prev = _context4.next) {
            case 0:
              tag = _ref6.tag;
              _context4.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])('/api/rest/v3/docket-tags/', {
                method: 'POST',
                body: {
                  tag: tag,
                  docket: docket
                }
              });

            case 3:
              return _context4.abrupt("return", _context4.sent);

            case 4:
            case "end":
              return _context4.stop();
          }
        }
      }, _callee4);
    }));

    return function (_x4) {
      return _ref7.apply(this, arguments);
    };
  }(), [docket]);
  var deleteAssoc = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref9 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee5(_ref8) {
      var assocId;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee5$(_context5) {
        while (1) {
          switch (_context5.prev = _context5.next) {
            case 0:
              assocId = _ref8.assocId;
              _context5.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])("/api/rest/v3/docket-tags/".concat(assocId, "/"), {
                method: 'DELETE'
              });

            case 3:
              return _context5.abrupt("return", _context5.sent);

            case 4:
            case "end":
              return _context5.stop();
          }
        }
      }, _callee5);
    }));

    return function (_x5) {
      return _ref9.apply(this, arguments);
    };
  }(), []);

  var _useQuery = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useQuery"])('associations', getAssociations, {
    enabled: enabled
  }),
      assocData = _useQuery.data;

  var associations = assocData ? assocData.results : [];

  var _useInfiniteQuery = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useInfiniteQuery"])('tags', getTags, {
    enabled: !!enabled,
    // if the lastPage has a next key, extract the page number
    getFetchMore: function getFetchMore(lastPage, allPages) {
      var nextPage = lastPage.next;
      if (!nextPage) return false;
      var matches = nextPage.match(/page=(\d+)/);
      return matches && matches[1] ? matches[1] : false;
    }
  }),
      status = _useInfiniteQuery.status,
      tags = _useInfiniteQuery.data,
      isFetching = _useInfiniteQuery.isFetching,
      isFetchingMore = _useInfiniteQuery.isFetchingMore,
      fetchMore = _useInfiniteQuery.fetchMore,
      canFetchMore = _useInfiniteQuery.canFetchMore;

  var _useMutation = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(deleteAssoc, {
    onSuccess: function onSuccess(data, variables) {
      // update the cache to remove the just-deleted association
      react_query__WEBPACK_IMPORTED_MODULE_6__["queryCache"].setQueryData('associations', function (old) {
        console.log(data, old);
        return _objectSpread(_objectSpread({}, old), {}, {
          results: old.results.filter(function (assoc) {
            return assoc.id !== variables.assocId;
          })
        });
      });
    }
  }),
      _useMutation2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation, 1),
      deleteAssociation = _useMutation2[0];

  var _useMutation3 = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(postAssoc, {
    onSuccess: function onSuccess(data, variables) {
      return (// update the cache to add the just created association
        react_query__WEBPACK_IMPORTED_MODULE_6__["queryCache"].setQueryData('associations', function (old) {
          console.log(data, old);
          return _objectSpread(_objectSpread({}, old), {}, {
            results: [].concat(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0___default()(old.results), [data])
          });
        })
      );
    }
  }),
      _useMutation4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation3, 1),
      addNewAssociation = _useMutation4[0];

  var _useMutation5 = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(postTag, {
    // if the new tag is created, update the cache to include the just-created tag
    // then fire the addNewAssociation mutation
    onSuccess: function onSuccess(data, variables) {
      setTextVal('');
      react_query__WEBPACK_IMPORTED_MODULE_6__["queryCache"].setQueryData('tags', function (old) {
        var keys = Object.keys(old);
        var lastKey = keys[keys.length - 1];
        var lastResult = old[lastKey];

        var newResult = _objectSpread(_objectSpread({}, lastResult), {}, {
          results: [].concat(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0___default()(lastResult.results), [_objectSpread(_objectSpread({}, data), {}, {
            dockets: [].concat(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0___default()(data.dockets), [docket])
          })])
        });

        return _objectSpread(_objectSpread({}, old), {}, _babel_runtime_helpers_defineProperty__WEBPACK_IMPORTED_MODULE_1___default()({}, lastKey, newResult));
      });
      addNewAssociation({
        tag: data.id
      });
    }
  }),
      _useMutation6 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation5, 1),
      addNewTag = _useMutation6[0]; // memoize the tag entries to reduce renders and apply the filter


  var filteredTags = react__WEBPACK_IMPORTED_MODULE_5___default.a.useMemo(function () {
    var flatTags = !tags ? [] : Object.entries(tags).map(function (_ref10) {
      var _ref11 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_ref10, 2),
          key = _ref11[0],
          apiResult = _ref11[1];

      return apiResult.results;
    }).flat(1); // rebuild tagData with the assocId

    var enhancedTags = flatTags.map(function (tag) {
      if (!associations) return tag;
      var assoc = associations.find(function (a) {
        return a.tag === tag.id;
      });
      return _objectSpread(_objectSpread({}, tag), {}, {
        assocId: assoc === null || assoc === void 0 ? void 0 : assoc.id
      });
    }); // case insensitive alpha sorting

    var sortedTags = enhancedTags.sort(function (a, b) {
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
    if (!textVal) return sortedTags;
    var exactMatch;
    var filtered = sortedTags.filter(function (tag) {
      if (!!textVal && tag.name === textVal) {
        exactMatch = true;
      }

      return tag.name.toLowerCase().includes(textVal.toLowerCase());
    });

    if (exactMatch) {
      return filtered;
    } else {
      // inject a create option to precede the listed tags
      return [{
        id: '-10',
        name: "Create Tag: ".concat(textVal),
        dockets: []
      }].concat(_babel_runtime_helpers_toConsumableArray__WEBPACK_IMPORTED_MODULE_0___default()(filtered));
    }
  }, [tags, textVal, associations]);
  return {
    infiniteQueryState: {
      status: status,
      canFetchMore: canFetchMore,
      isFetching: isFetching,
      isFetchingMore: isFetchingMore,
      fetchMore: fetchMore
    },
    tags: filteredTags,
    textVal: textVal,
    setTextVal: setTextVal,
    associations: associations,
    addNewTag: addNewTag,
    addNewAssociation: addNewAssociation,
    deleteAssociation: deleteAssociation
  };
};
var updateTags = function updateTags() {
  //  Update our tag fields
  var updateTag = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref12 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee6(tag) {
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee6$(_context6) {
        while (1) {
          switch (_context6.prev = _context6.next) {
            case 0:
              _context6.next = 2;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])("/api/rest/v3/tags/".concat(tag.id, "/"), {
                method: 'PUT',
                body: _objectSpread({}, tag)
              });

            case 2:
              return _context6.abrupt("return", _context6.sent);

            case 3:
            case "end":
              return _context6.stop();
          }
        }
      }, _callee6);
    }));

    return function (_x6) {
      return _ref12.apply(this, arguments);
    };
  }(), []);
  var deleteTag = react__WEBPACK_IMPORTED_MODULE_5___default.a.useCallback( /*#__PURE__*/function () {
    var _ref13 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_3___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.mark(function _callee7(id) {
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_2___default.a.wrap(function _callee7$(_context7) {
        while (1) {
          switch (_context7.prev = _context7.next) {
            case 0:
              _context7.next = 2;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_7__["appFetch"])("/api/rest/v3/tags/".concat(id, "/"), {
                method: 'DELETE'
              });

            case 2:
              return _context7.abrupt("return", _context7.sent);

            case 3:
            case "end":
              return _context7.stop();
          }
        }
      }, _callee7);
    }));

    return function (_x7) {
      return _ref13.apply(this, arguments);
    };
  }(), []);

  var _useMutation7 = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(deleteTag, {
    // To update a description - if successful log it.
    onSuccess: function onSuccess(data, variables) {
      console.log("Successfully deletion");
    }
  }),
      _useMutation8 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation7, 1),
      deleteTags = _useMutation8[0];

  var _useMutation9 = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(updateTag, {
    // To update a description or publication status
    onSuccess: function onSuccess(data, variables) {
      console.log("Successful update to Tag");
    }
  }),
      _useMutation10 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation9, 1),
      modifyTags = _useMutation10[0];

  return {
    modifyTags: modifyTags,
    deleteTags: deleteTags
  };
};

/***/ }),

/***/ "./assets/react/index.tsx":
/*!********************************!*\
  !*** ./assets/react/index.tsx ***!
  \********************************/
/*! no exports provided */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var react_dom__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! react-dom */ "./node_modules/react-dom/index.js");
/* harmony import */ var react_dom__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(react_dom__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var react_router_dom__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! react-router-dom */ "./node_modules/react-router-dom/esm/react-router-dom.js");
/* harmony import */ var _TagSelect__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! ./TagSelect */ "./assets/react/TagSelect.tsx");
/* harmony import */ var _TagList__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! ./TagList */ "./assets/react/TagList.tsx");
/* harmony import */ var _TagPage__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./TagPage */ "./assets/react/TagPage.tsx");







function getDataFromReactRoot() {
  var div = document.querySelector('div#react-root');

  if (div && div instanceof HTMLElement) {
    var authStr = div.dataset.authenticated;
    if (!authStr) return {};
    var strParts = authStr.split(':', 2);
    return {
      userId: parseInt(strParts[0], 10),
      userName: strParts[1],
      editUrl: div.dataset.editUrl,
      isPageOwner: div.dataset.isPageOwner != ''
    };
  } else {
    console.error('Unable to fetch credentials from server. Tags disabled.');
    return {};
  }
}

var App = function App() {
  var root = document.getElementById('react-root');
  var data = JSON.parse(JSON.stringify(root.dataset));
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["BrowserRouter"], null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Switch"], null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Route"], {
    path: "/docket"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_TagSelect__WEBPACK_IMPORTED_MODULE_3__["default"], data)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Route"], {
    exact: true,
    path: "/tags/:userName/"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_TagList__WEBPACK_IMPORTED_MODULE_4__["default"], {
    userId: data.requestedUserId,
    userName: data.requestedUser,
    isPageOwner: data.isPageOwner
  })), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Route"], {
    path: "/tags/:userName/:id"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_TagPage__WEBPACK_IMPORTED_MODULE_5__["TagMarkdown"], data))));
};

react_dom__WEBPACK_IMPORTED_MODULE_1___default.a.render( /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_0___default.a.StrictMode, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(App, null)), document.getElementById('react-root'));

/***/ }),

/***/ "./assets/react/tag-page.css":
/*!***********************************!*\
  !*** ./assets/react/tag-page.css ***!
  \***********************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../node_modules/style-loader/dist/runtime/injectStylesIntoStyleTag.js */ "./node_modules/style-loader/dist/runtime/injectStylesIntoStyleTag.js");
/* harmony import */ var _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! !../../node_modules/css-loader/dist/cjs.js!./tag-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/tag-page.css");

            

var options = {};

options.insert = "head";
options.singleton = false;

var update = _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0___default()(_node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"], options);



/* harmony default export */ __webpack_exports__["default"] = (_node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals || {});

/***/ }),

/***/ "./node_modules/css-loader/dist/cjs.js!./assets/react/tag-page.css":
/*!*************************************************************************!*\
  !*** ./node_modules/css-loader/dist/cjs.js!./assets/react/tag-page.css ***!
  \*************************************************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_css_loader_dist_runtime_cssWithMappingToString_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../node_modules/css-loader/dist/runtime/cssWithMappingToString.js */ "./node_modules/css-loader/dist/runtime/cssWithMappingToString.js");
/* harmony import */ var _node_modules_css_loader_dist_runtime_cssWithMappingToString_js__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_node_modules_css_loader_dist_runtime_cssWithMappingToString_js__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _node_modules_css_loader_dist_runtime_api_js__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! ../../node_modules/css-loader/dist/runtime/api.js */ "./node_modules/css-loader/dist/runtime/api.js");
/* harmony import */ var _node_modules_css_loader_dist_runtime_api_js__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_node_modules_css_loader_dist_runtime_api_js__WEBPACK_IMPORTED_MODULE_1__);
// Imports


var ___CSS_LOADER_EXPORT___ = _node_modules_css_loader_dist_runtime_api_js__WEBPACK_IMPORTED_MODULE_1___default()(_node_modules_css_loader_dist_runtime_cssWithMappingToString_js__WEBPACK_IMPORTED_MODULE_0___default.a);
// Module
___CSS_LOADER_EXPORT___.push([module.i, "\n.editor-toolbar {\n  border-top: none !important;\n  border-top-left-radius: 0px !important;\n  border-top-right-radius: 0px !important;\n  border-left: 1px solid lightgray;\n  border-right: 1px solid lightgray;\n}\n\n#markdown_viewer {\n  border: 1px solid;\n  border-color: lightgrey;\n  padding: 10px;\n  min-height: 100px;\n  border-top: none;\n}\n\n.view-only {\n  margin-top: 50px !important;\n  border: none !important;\n}\n\n#tab-tabs {\n    margin-top: 40px !important;\n}\n\n#markdown_viewer table, #markdown_viewer thead, #markdown_viewer tbody, #markdown_viewer tr, #markdown_viewer td, #markdown_viewer th {\n  border: 1px solid;\n  padding:5px;\n}\n\n#left-tabs-example > ul > li > a:focus {\n   outline: none;\n}\n\n#save_button {\n  border: none;\n}\n\ntd  {\n  vertical-align: middle;\n}\n\nli:focus {\n  outline: 0;\n}\na:focus {\n  outline: 0;\n}\n\n.btn-sm {\n  font-size: 10px;\n  line-height: 1.0 !important;\n}\n\nlabel.toggle input span {\n  border-radius: 2px !important;\n}\n\nlabel.toggle {\n  vertical-align: text-top;\n  height: 16px;\n  width: 28px;\n}\n\n", "",{"version":3,"sources":["webpack://./assets/react/tag-page.css"],"names":[],"mappings":";AACA;EACE,2BAA2B;EAC3B,sCAAsC;EACtC,uCAAuC;EACvC,gCAAgC;EAChC,iCAAiC;AACnC;;AAEA;EACE,iBAAiB;EACjB,uBAAuB;EACvB,aAAa;EACb,iBAAiB;EACjB,gBAAgB;AAClB;;AAEA;EACE,2BAA2B;EAC3B,uBAAuB;AACzB;;AAEA;IACI,2BAA2B;AAC/B;;AAEA;EACE,iBAAiB;EACjB,WAAW;AACb;;AAEA;GACG,aAAa;AAChB;;AAEA;EACE,YAAY;AACd;;AAEA;EACE,sBAAsB;AACxB;;AAEA;EACE,UAAU;AACZ;AACA;EACE,UAAU;AACZ;;AAEA;EACE,eAAe;EACf,2BAA2B;AAC7B;;AAEA;EACE,6BAA6B;AAC/B;;AAEA;EACE,wBAAwB;EACxB,YAAY;EACZ,WAAW;AACb","sourcesContent":["\n.editor-toolbar {\n  border-top: none !important;\n  border-top-left-radius: 0px !important;\n  border-top-right-radius: 0px !important;\n  border-left: 1px solid lightgray;\n  border-right: 1px solid lightgray;\n}\n\n#markdown_viewer {\n  border: 1px solid;\n  border-color: lightgrey;\n  padding: 10px;\n  min-height: 100px;\n  border-top: none;\n}\n\n.view-only {\n  margin-top: 50px !important;\n  border: none !important;\n}\n\n#tab-tabs {\n    margin-top: 40px !important;\n}\n\n#markdown_viewer table, #markdown_viewer thead, #markdown_viewer tbody, #markdown_viewer tr, #markdown_viewer td, #markdown_viewer th {\n  border: 1px solid;\n  padding:5px;\n}\n\n#left-tabs-example > ul > li > a:focus {\n   outline: none;\n}\n\n#save_button {\n  border: none;\n}\n\ntd  {\n  vertical-align: middle;\n}\n\nli:focus {\n  outline: 0;\n}\na:focus {\n  outline: 0;\n}\n\n.btn-sm {\n  font-size: 10px;\n  line-height: 1.0 !important;\n}\n\nlabel.toggle input span {\n  border-radius: 2px !important;\n}\n\nlabel.toggle {\n  vertical-align: text-top;\n  height: 16px;\n  width: 28px;\n}\n\n"],"sourceRoot":""}]);
// Exports
/* harmony default export */ __webpack_exports__["default"] = (___CSS_LOADER_EXPORT___);


/***/ }),

/***/ 0:
/*!**********************************!*\
  !*** multi ./assets/react/index ***!
  \**********************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

module.exports = __webpack_require__(/*! ./assets/react/index */"./assets/react/index.tsx");


/***/ }),

/***/ 1:
/*!********************!*\
  !*** fs (ignored) ***!
  \********************/
/*! no static exports found */
/***/ (function(module, exports) {

/* (ignored) */

/***/ })

/******/ });
//# sourceMappingURL=main.js.map