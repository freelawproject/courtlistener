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
/******/ 	function hotDisposeChunk(chunkId) {
/******/ 		delete installedChunks[chunkId];
/******/ 	}
/******/ 	var parentHotUpdateCallback = window["webpackHotUpdate"];
/******/ 	window["webpackHotUpdate"] = // eslint-disable-next-line no-unused-vars
/******/ 	function webpackHotUpdateCallback(chunkId, moreModules) {
/******/ 		hotAddUpdateChunk(chunkId, moreModules);
/******/ 		if (parentHotUpdateCallback) parentHotUpdateCallback(chunkId, moreModules);
/******/ 	} ;
/******/
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	function hotDownloadUpdateChunk(chunkId) {
/******/ 		var script = document.createElement("script");
/******/ 		script.charset = "utf-8";
/******/ 		script.src = __webpack_require__.p + "" + chunkId + "." + hotCurrentHash + ".hot-update.js";
/******/ 		if (null) script.crossOrigin = null;
/******/ 		document.head.appendChild(script);
/******/ 	}
/******/
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	function hotDownloadManifest(requestTimeout) {
/******/ 		requestTimeout = requestTimeout || 10000;
/******/ 		return new Promise(function(resolve, reject) {
/******/ 			if (typeof XMLHttpRequest === "undefined") {
/******/ 				return reject(new Error("No browser support"));
/******/ 			}
/******/ 			try {
/******/ 				var request = new XMLHttpRequest();
/******/ 				var requestPath = __webpack_require__.p + "" + hotCurrentHash + ".hot-update.json";
/******/ 				request.open("GET", requestPath, true);
/******/ 				request.timeout = requestTimeout;
/******/ 				request.send(null);
/******/ 			} catch (err) {
/******/ 				return reject(err);
/******/ 			}
/******/ 			request.onreadystatechange = function() {
/******/ 				if (request.readyState !== 4) return;
/******/ 				if (request.status === 0) {
/******/ 					// timeout
/******/ 					reject(
/******/ 						new Error("Manifest request to " + requestPath + " timed out.")
/******/ 					);
/******/ 				} else if (request.status === 404) {
/******/ 					// no update available
/******/ 					resolve();
/******/ 				} else if (request.status !== 200 && request.status !== 304) {
/******/ 					// other failure
/******/ 					reject(new Error("Manifest request to " + requestPath + " failed."));
/******/ 				} else {
/******/ 					// success
/******/ 					try {
/******/ 						var update = JSON.parse(request.responseText);
/******/ 					} catch (e) {
/******/ 						reject(e);
/******/ 						return;
/******/ 					}
/******/ 					resolve(update);
/******/ 				}
/******/ 			};
/******/ 		});
/******/ 	}
/******/
/******/ 	var hotApplyOnUpdate = true;
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	var hotCurrentHash = "46490bb9d79dc7a356be";
/******/ 	var hotRequestTimeout = 10000;
/******/ 	var hotCurrentModuleData = {};
/******/ 	var hotCurrentChildModule;
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	var hotCurrentParents = [];
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	var hotCurrentParentsTemp = [];
/******/
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	function hotCreateRequire(moduleId) {
/******/ 		var me = installedModules[moduleId];
/******/ 		if (!me) return __webpack_require__;
/******/ 		var fn = function(request) {
/******/ 			if (me.hot.active) {
/******/ 				if (installedModules[request]) {
/******/ 					if (installedModules[request].parents.indexOf(moduleId) === -1) {
/******/ 						installedModules[request].parents.push(moduleId);
/******/ 					}
/******/ 				} else {
/******/ 					hotCurrentParents = [moduleId];
/******/ 					hotCurrentChildModule = request;
/******/ 				}
/******/ 				if (me.children.indexOf(request) === -1) {
/******/ 					me.children.push(request);
/******/ 				}
/******/ 			} else {
/******/ 				console.warn(
/******/ 					"[HMR] unexpected require(" +
/******/ 						request +
/******/ 						") from disposed module " +
/******/ 						moduleId
/******/ 				);
/******/ 				hotCurrentParents = [];
/******/ 			}
/******/ 			return __webpack_require__(request);
/******/ 		};
/******/ 		var ObjectFactory = function ObjectFactory(name) {
/******/ 			return {
/******/ 				configurable: true,
/******/ 				enumerable: true,
/******/ 				get: function() {
/******/ 					return __webpack_require__[name];
/******/ 				},
/******/ 				set: function(value) {
/******/ 					__webpack_require__[name] = value;
/******/ 				}
/******/ 			};
/******/ 		};
/******/ 		for (var name in __webpack_require__) {
/******/ 			if (
/******/ 				Object.prototype.hasOwnProperty.call(__webpack_require__, name) &&
/******/ 				name !== "e" &&
/******/ 				name !== "t"
/******/ 			) {
/******/ 				Object.defineProperty(fn, name, ObjectFactory(name));
/******/ 			}
/******/ 		}
/******/ 		fn.e = function(chunkId) {
/******/ 			if (hotStatus === "ready") hotSetStatus("prepare");
/******/ 			hotChunksLoading++;
/******/ 			return __webpack_require__.e(chunkId).then(finishChunkLoading, function(err) {
/******/ 				finishChunkLoading();
/******/ 				throw err;
/******/ 			});
/******/
/******/ 			function finishChunkLoading() {
/******/ 				hotChunksLoading--;
/******/ 				if (hotStatus === "prepare") {
/******/ 					if (!hotWaitingFilesMap[chunkId]) {
/******/ 						hotEnsureUpdateChunk(chunkId);
/******/ 					}
/******/ 					if (hotChunksLoading === 0 && hotWaitingFiles === 0) {
/******/ 						hotUpdateDownloaded();
/******/ 					}
/******/ 				}
/******/ 			}
/******/ 		};
/******/ 		fn.t = function(value, mode) {
/******/ 			if (mode & 1) value = fn(value);
/******/ 			return __webpack_require__.t(value, mode & ~1);
/******/ 		};
/******/ 		return fn;
/******/ 	}
/******/
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	function hotCreateModule(moduleId) {
/******/ 		var hot = {
/******/ 			// private stuff
/******/ 			_acceptedDependencies: {},
/******/ 			_declinedDependencies: {},
/******/ 			_selfAccepted: false,
/******/ 			_selfDeclined: false,
/******/ 			_selfInvalidated: false,
/******/ 			_disposeHandlers: [],
/******/ 			_main: hotCurrentChildModule !== moduleId,
/******/
/******/ 			// Module API
/******/ 			active: true,
/******/ 			accept: function(dep, callback) {
/******/ 				if (dep === undefined) hot._selfAccepted = true;
/******/ 				else if (typeof dep === "function") hot._selfAccepted = dep;
/******/ 				else if (typeof dep === "object")
/******/ 					for (var i = 0; i < dep.length; i++)
/******/ 						hot._acceptedDependencies[dep[i]] = callback || function() {};
/******/ 				else hot._acceptedDependencies[dep] = callback || function() {};
/******/ 			},
/******/ 			decline: function(dep) {
/******/ 				if (dep === undefined) hot._selfDeclined = true;
/******/ 				else if (typeof dep === "object")
/******/ 					for (var i = 0; i < dep.length; i++)
/******/ 						hot._declinedDependencies[dep[i]] = true;
/******/ 				else hot._declinedDependencies[dep] = true;
/******/ 			},
/******/ 			dispose: function(callback) {
/******/ 				hot._disposeHandlers.push(callback);
/******/ 			},
/******/ 			addDisposeHandler: function(callback) {
/******/ 				hot._disposeHandlers.push(callback);
/******/ 			},
/******/ 			removeDisposeHandler: function(callback) {
/******/ 				var idx = hot._disposeHandlers.indexOf(callback);
/******/ 				if (idx >= 0) hot._disposeHandlers.splice(idx, 1);
/******/ 			},
/******/ 			invalidate: function() {
/******/ 				this._selfInvalidated = true;
/******/ 				switch (hotStatus) {
/******/ 					case "idle":
/******/ 						hotUpdate = {};
/******/ 						hotUpdate[moduleId] = modules[moduleId];
/******/ 						hotSetStatus("ready");
/******/ 						break;
/******/ 					case "ready":
/******/ 						hotApplyInvalidatedModule(moduleId);
/******/ 						break;
/******/ 					case "prepare":
/******/ 					case "check":
/******/ 					case "dispose":
/******/ 					case "apply":
/******/ 						(hotQueuedInvalidatedModules =
/******/ 							hotQueuedInvalidatedModules || []).push(moduleId);
/******/ 						break;
/******/ 					default:
/******/ 						// ignore requests in error states
/******/ 						break;
/******/ 				}
/******/ 			},
/******/
/******/ 			// Management API
/******/ 			check: hotCheck,
/******/ 			apply: hotApply,
/******/ 			status: function(l) {
/******/ 				if (!l) return hotStatus;
/******/ 				hotStatusHandlers.push(l);
/******/ 			},
/******/ 			addStatusHandler: function(l) {
/******/ 				hotStatusHandlers.push(l);
/******/ 			},
/******/ 			removeStatusHandler: function(l) {
/******/ 				var idx = hotStatusHandlers.indexOf(l);
/******/ 				if (idx >= 0) hotStatusHandlers.splice(idx, 1);
/******/ 			},
/******/
/******/ 			//inherit from previous dispose call
/******/ 			data: hotCurrentModuleData[moduleId]
/******/ 		};
/******/ 		hotCurrentChildModule = undefined;
/******/ 		return hot;
/******/ 	}
/******/
/******/ 	var hotStatusHandlers = [];
/******/ 	var hotStatus = "idle";
/******/
/******/ 	function hotSetStatus(newStatus) {
/******/ 		hotStatus = newStatus;
/******/ 		for (var i = 0; i < hotStatusHandlers.length; i++)
/******/ 			hotStatusHandlers[i].call(null, newStatus);
/******/ 	}
/******/
/******/ 	// while downloading
/******/ 	var hotWaitingFiles = 0;
/******/ 	var hotChunksLoading = 0;
/******/ 	var hotWaitingFilesMap = {};
/******/ 	var hotRequestedFilesMap = {};
/******/ 	var hotAvailableFilesMap = {};
/******/ 	var hotDeferred;
/******/
/******/ 	// The update info
/******/ 	var hotUpdate, hotUpdateNewHash, hotQueuedInvalidatedModules;
/******/
/******/ 	function toModuleId(id) {
/******/ 		var isNumber = +id + "" === id;
/******/ 		return isNumber ? +id : id;
/******/ 	}
/******/
/******/ 	function hotCheck(apply) {
/******/ 		if (hotStatus !== "idle") {
/******/ 			throw new Error("check() is only allowed in idle status");
/******/ 		}
/******/ 		hotApplyOnUpdate = apply;
/******/ 		hotSetStatus("check");
/******/ 		return hotDownloadManifest(hotRequestTimeout).then(function(update) {
/******/ 			if (!update) {
/******/ 				hotSetStatus(hotApplyInvalidatedModules() ? "ready" : "idle");
/******/ 				return null;
/******/ 			}
/******/ 			hotRequestedFilesMap = {};
/******/ 			hotWaitingFilesMap = {};
/******/ 			hotAvailableFilesMap = update.c;
/******/ 			hotUpdateNewHash = update.h;
/******/
/******/ 			hotSetStatus("prepare");
/******/ 			var promise = new Promise(function(resolve, reject) {
/******/ 				hotDeferred = {
/******/ 					resolve: resolve,
/******/ 					reject: reject
/******/ 				};
/******/ 			});
/******/ 			hotUpdate = {};
/******/ 			for(var chunkId in installedChunks)
/******/ 			// eslint-disable-next-line no-lone-blocks
/******/ 			{
/******/ 				hotEnsureUpdateChunk(chunkId);
/******/ 			}
/******/ 			if (
/******/ 				hotStatus === "prepare" &&
/******/ 				hotChunksLoading === 0 &&
/******/ 				hotWaitingFiles === 0
/******/ 			) {
/******/ 				hotUpdateDownloaded();
/******/ 			}
/******/ 			return promise;
/******/ 		});
/******/ 	}
/******/
/******/ 	// eslint-disable-next-line no-unused-vars
/******/ 	function hotAddUpdateChunk(chunkId, moreModules) {
/******/ 		if (!hotAvailableFilesMap[chunkId] || !hotRequestedFilesMap[chunkId])
/******/ 			return;
/******/ 		hotRequestedFilesMap[chunkId] = false;
/******/ 		for (var moduleId in moreModules) {
/******/ 			if (Object.prototype.hasOwnProperty.call(moreModules, moduleId)) {
/******/ 				hotUpdate[moduleId] = moreModules[moduleId];
/******/ 			}
/******/ 		}
/******/ 		if (--hotWaitingFiles === 0 && hotChunksLoading === 0) {
/******/ 			hotUpdateDownloaded();
/******/ 		}
/******/ 	}
/******/
/******/ 	function hotEnsureUpdateChunk(chunkId) {
/******/ 		if (!hotAvailableFilesMap[chunkId]) {
/******/ 			hotWaitingFilesMap[chunkId] = true;
/******/ 		} else {
/******/ 			hotRequestedFilesMap[chunkId] = true;
/******/ 			hotWaitingFiles++;
/******/ 			hotDownloadUpdateChunk(chunkId);
/******/ 		}
/******/ 	}
/******/
/******/ 	function hotUpdateDownloaded() {
/******/ 		hotSetStatus("ready");
/******/ 		var deferred = hotDeferred;
/******/ 		hotDeferred = null;
/******/ 		if (!deferred) return;
/******/ 		if (hotApplyOnUpdate) {
/******/ 			// Wrap deferred object in Promise to mark it as a well-handled Promise to
/******/ 			// avoid triggering uncaught exception warning in Chrome.
/******/ 			// See https://bugs.chromium.org/p/chromium/issues/detail?id=465666
/******/ 			Promise.resolve()
/******/ 				.then(function() {
/******/ 					return hotApply(hotApplyOnUpdate);
/******/ 				})
/******/ 				.then(
/******/ 					function(result) {
/******/ 						deferred.resolve(result);
/******/ 					},
/******/ 					function(err) {
/******/ 						deferred.reject(err);
/******/ 					}
/******/ 				);
/******/ 		} else {
/******/ 			var outdatedModules = [];
/******/ 			for (var id in hotUpdate) {
/******/ 				if (Object.prototype.hasOwnProperty.call(hotUpdate, id)) {
/******/ 					outdatedModules.push(toModuleId(id));
/******/ 				}
/******/ 			}
/******/ 			deferred.resolve(outdatedModules);
/******/ 		}
/******/ 	}
/******/
/******/ 	function hotApply(options) {
/******/ 		if (hotStatus !== "ready")
/******/ 			throw new Error("apply() is only allowed in ready status");
/******/ 		options = options || {};
/******/ 		return hotApplyInternal(options);
/******/ 	}
/******/
/******/ 	function hotApplyInternal(options) {
/******/ 		hotApplyInvalidatedModules();
/******/
/******/ 		var cb;
/******/ 		var i;
/******/ 		var j;
/******/ 		var module;
/******/ 		var moduleId;
/******/
/******/ 		function getAffectedStuff(updateModuleId) {
/******/ 			var outdatedModules = [updateModuleId];
/******/ 			var outdatedDependencies = {};
/******/
/******/ 			var queue = outdatedModules.map(function(id) {
/******/ 				return {
/******/ 					chain: [id],
/******/ 					id: id
/******/ 				};
/******/ 			});
/******/ 			while (queue.length > 0) {
/******/ 				var queueItem = queue.pop();
/******/ 				var moduleId = queueItem.id;
/******/ 				var chain = queueItem.chain;
/******/ 				module = installedModules[moduleId];
/******/ 				if (
/******/ 					!module ||
/******/ 					(module.hot._selfAccepted && !module.hot._selfInvalidated)
/******/ 				)
/******/ 					continue;
/******/ 				if (module.hot._selfDeclined) {
/******/ 					return {
/******/ 						type: "self-declined",
/******/ 						chain: chain,
/******/ 						moduleId: moduleId
/******/ 					};
/******/ 				}
/******/ 				if (module.hot._main) {
/******/ 					return {
/******/ 						type: "unaccepted",
/******/ 						chain: chain,
/******/ 						moduleId: moduleId
/******/ 					};
/******/ 				}
/******/ 				for (var i = 0; i < module.parents.length; i++) {
/******/ 					var parentId = module.parents[i];
/******/ 					var parent = installedModules[parentId];
/******/ 					if (!parent) continue;
/******/ 					if (parent.hot._declinedDependencies[moduleId]) {
/******/ 						return {
/******/ 							type: "declined",
/******/ 							chain: chain.concat([parentId]),
/******/ 							moduleId: moduleId,
/******/ 							parentId: parentId
/******/ 						};
/******/ 					}
/******/ 					if (outdatedModules.indexOf(parentId) !== -1) continue;
/******/ 					if (parent.hot._acceptedDependencies[moduleId]) {
/******/ 						if (!outdatedDependencies[parentId])
/******/ 							outdatedDependencies[parentId] = [];
/******/ 						addAllToSet(outdatedDependencies[parentId], [moduleId]);
/******/ 						continue;
/******/ 					}
/******/ 					delete outdatedDependencies[parentId];
/******/ 					outdatedModules.push(parentId);
/******/ 					queue.push({
/******/ 						chain: chain.concat([parentId]),
/******/ 						id: parentId
/******/ 					});
/******/ 				}
/******/ 			}
/******/
/******/ 			return {
/******/ 				type: "accepted",
/******/ 				moduleId: updateModuleId,
/******/ 				outdatedModules: outdatedModules,
/******/ 				outdatedDependencies: outdatedDependencies
/******/ 			};
/******/ 		}
/******/
/******/ 		function addAllToSet(a, b) {
/******/ 			for (var i = 0; i < b.length; i++) {
/******/ 				var item = b[i];
/******/ 				if (a.indexOf(item) === -1) a.push(item);
/******/ 			}
/******/ 		}
/******/
/******/ 		// at begin all updates modules are outdated
/******/ 		// the "outdated" status can propagate to parents if they don't accept the children
/******/ 		var outdatedDependencies = {};
/******/ 		var outdatedModules = [];
/******/ 		var appliedUpdate = {};
/******/
/******/ 		var warnUnexpectedRequire = function warnUnexpectedRequire() {
/******/ 			console.warn(
/******/ 				"[HMR] unexpected require(" + result.moduleId + ") to disposed module"
/******/ 			);
/******/ 		};
/******/
/******/ 		for (var id in hotUpdate) {
/******/ 			if (Object.prototype.hasOwnProperty.call(hotUpdate, id)) {
/******/ 				moduleId = toModuleId(id);
/******/ 				/** @type {TODO} */
/******/ 				var result;
/******/ 				if (hotUpdate[id]) {
/******/ 					result = getAffectedStuff(moduleId);
/******/ 				} else {
/******/ 					result = {
/******/ 						type: "disposed",
/******/ 						moduleId: id
/******/ 					};
/******/ 				}
/******/ 				/** @type {Error|false} */
/******/ 				var abortError = false;
/******/ 				var doApply = false;
/******/ 				var doDispose = false;
/******/ 				var chainInfo = "";
/******/ 				if (result.chain) {
/******/ 					chainInfo = "\nUpdate propagation: " + result.chain.join(" -> ");
/******/ 				}
/******/ 				switch (result.type) {
/******/ 					case "self-declined":
/******/ 						if (options.onDeclined) options.onDeclined(result);
/******/ 						if (!options.ignoreDeclined)
/******/ 							abortError = new Error(
/******/ 								"Aborted because of self decline: " +
/******/ 									result.moduleId +
/******/ 									chainInfo
/******/ 							);
/******/ 						break;
/******/ 					case "declined":
/******/ 						if (options.onDeclined) options.onDeclined(result);
/******/ 						if (!options.ignoreDeclined)
/******/ 							abortError = new Error(
/******/ 								"Aborted because of declined dependency: " +
/******/ 									result.moduleId +
/******/ 									" in " +
/******/ 									result.parentId +
/******/ 									chainInfo
/******/ 							);
/******/ 						break;
/******/ 					case "unaccepted":
/******/ 						if (options.onUnaccepted) options.onUnaccepted(result);
/******/ 						if (!options.ignoreUnaccepted)
/******/ 							abortError = new Error(
/******/ 								"Aborted because " + moduleId + " is not accepted" + chainInfo
/******/ 							);
/******/ 						break;
/******/ 					case "accepted":
/******/ 						if (options.onAccepted) options.onAccepted(result);
/******/ 						doApply = true;
/******/ 						break;
/******/ 					case "disposed":
/******/ 						if (options.onDisposed) options.onDisposed(result);
/******/ 						doDispose = true;
/******/ 						break;
/******/ 					default:
/******/ 						throw new Error("Unexception type " + result.type);
/******/ 				}
/******/ 				if (abortError) {
/******/ 					hotSetStatus("abort");
/******/ 					return Promise.reject(abortError);
/******/ 				}
/******/ 				if (doApply) {
/******/ 					appliedUpdate[moduleId] = hotUpdate[moduleId];
/******/ 					addAllToSet(outdatedModules, result.outdatedModules);
/******/ 					for (moduleId in result.outdatedDependencies) {
/******/ 						if (
/******/ 							Object.prototype.hasOwnProperty.call(
/******/ 								result.outdatedDependencies,
/******/ 								moduleId
/******/ 							)
/******/ 						) {
/******/ 							if (!outdatedDependencies[moduleId])
/******/ 								outdatedDependencies[moduleId] = [];
/******/ 							addAllToSet(
/******/ 								outdatedDependencies[moduleId],
/******/ 								result.outdatedDependencies[moduleId]
/******/ 							);
/******/ 						}
/******/ 					}
/******/ 				}
/******/ 				if (doDispose) {
/******/ 					addAllToSet(outdatedModules, [result.moduleId]);
/******/ 					appliedUpdate[moduleId] = warnUnexpectedRequire;
/******/ 				}
/******/ 			}
/******/ 		}
/******/
/******/ 		// Store self accepted outdated modules to require them later by the module system
/******/ 		var outdatedSelfAcceptedModules = [];
/******/ 		for (i = 0; i < outdatedModules.length; i++) {
/******/ 			moduleId = outdatedModules[i];
/******/ 			if (
/******/ 				installedModules[moduleId] &&
/******/ 				installedModules[moduleId].hot._selfAccepted &&
/******/ 				// removed self-accepted modules should not be required
/******/ 				appliedUpdate[moduleId] !== warnUnexpectedRequire &&
/******/ 				// when called invalidate self-accepting is not possible
/******/ 				!installedModules[moduleId].hot._selfInvalidated
/******/ 			) {
/******/ 				outdatedSelfAcceptedModules.push({
/******/ 					module: moduleId,
/******/ 					parents: installedModules[moduleId].parents.slice(),
/******/ 					errorHandler: installedModules[moduleId].hot._selfAccepted
/******/ 				});
/******/ 			}
/******/ 		}
/******/
/******/ 		// Now in "dispose" phase
/******/ 		hotSetStatus("dispose");
/******/ 		Object.keys(hotAvailableFilesMap).forEach(function(chunkId) {
/******/ 			if (hotAvailableFilesMap[chunkId] === false) {
/******/ 				hotDisposeChunk(chunkId);
/******/ 			}
/******/ 		});
/******/
/******/ 		var idx;
/******/ 		var queue = outdatedModules.slice();
/******/ 		while (queue.length > 0) {
/******/ 			moduleId = queue.pop();
/******/ 			module = installedModules[moduleId];
/******/ 			if (!module) continue;
/******/
/******/ 			var data = {};
/******/
/******/ 			// Call dispose handlers
/******/ 			var disposeHandlers = module.hot._disposeHandlers;
/******/ 			for (j = 0; j < disposeHandlers.length; j++) {
/******/ 				cb = disposeHandlers[j];
/******/ 				cb(data);
/******/ 			}
/******/ 			hotCurrentModuleData[moduleId] = data;
/******/
/******/ 			// disable module (this disables requires from this module)
/******/ 			module.hot.active = false;
/******/
/******/ 			// remove module from cache
/******/ 			delete installedModules[moduleId];
/******/
/******/ 			// when disposing there is no need to call dispose handler
/******/ 			delete outdatedDependencies[moduleId];
/******/
/******/ 			// remove "parents" references from all children
/******/ 			for (j = 0; j < module.children.length; j++) {
/******/ 				var child = installedModules[module.children[j]];
/******/ 				if (!child) continue;
/******/ 				idx = child.parents.indexOf(moduleId);
/******/ 				if (idx >= 0) {
/******/ 					child.parents.splice(idx, 1);
/******/ 				}
/******/ 			}
/******/ 		}
/******/
/******/ 		// remove outdated dependency from module children
/******/ 		var dependency;
/******/ 		var moduleOutdatedDependencies;
/******/ 		for (moduleId in outdatedDependencies) {
/******/ 			if (
/******/ 				Object.prototype.hasOwnProperty.call(outdatedDependencies, moduleId)
/******/ 			) {
/******/ 				module = installedModules[moduleId];
/******/ 				if (module) {
/******/ 					moduleOutdatedDependencies = outdatedDependencies[moduleId];
/******/ 					for (j = 0; j < moduleOutdatedDependencies.length; j++) {
/******/ 						dependency = moduleOutdatedDependencies[j];
/******/ 						idx = module.children.indexOf(dependency);
/******/ 						if (idx >= 0) module.children.splice(idx, 1);
/******/ 					}
/******/ 				}
/******/ 			}
/******/ 		}
/******/
/******/ 		// Now in "apply" phase
/******/ 		hotSetStatus("apply");
/******/
/******/ 		if (hotUpdateNewHash !== undefined) {
/******/ 			hotCurrentHash = hotUpdateNewHash;
/******/ 			hotUpdateNewHash = undefined;
/******/ 		}
/******/ 		hotUpdate = undefined;
/******/
/******/ 		// insert new code
/******/ 		for (moduleId in appliedUpdate) {
/******/ 			if (Object.prototype.hasOwnProperty.call(appliedUpdate, moduleId)) {
/******/ 				modules[moduleId] = appliedUpdate[moduleId];
/******/ 			}
/******/ 		}
/******/
/******/ 		// call accept handlers
/******/ 		var error = null;
/******/ 		for (moduleId in outdatedDependencies) {
/******/ 			if (
/******/ 				Object.prototype.hasOwnProperty.call(outdatedDependencies, moduleId)
/******/ 			) {
/******/ 				module = installedModules[moduleId];
/******/ 				if (module) {
/******/ 					moduleOutdatedDependencies = outdatedDependencies[moduleId];
/******/ 					var callbacks = [];
/******/ 					for (i = 0; i < moduleOutdatedDependencies.length; i++) {
/******/ 						dependency = moduleOutdatedDependencies[i];
/******/ 						cb = module.hot._acceptedDependencies[dependency];
/******/ 						if (cb) {
/******/ 							if (callbacks.indexOf(cb) !== -1) continue;
/******/ 							callbacks.push(cb);
/******/ 						}
/******/ 					}
/******/ 					for (i = 0; i < callbacks.length; i++) {
/******/ 						cb = callbacks[i];
/******/ 						try {
/******/ 							cb(moduleOutdatedDependencies);
/******/ 						} catch (err) {
/******/ 							if (options.onErrored) {
/******/ 								options.onErrored({
/******/ 									type: "accept-errored",
/******/ 									moduleId: moduleId,
/******/ 									dependencyId: moduleOutdatedDependencies[i],
/******/ 									error: err
/******/ 								});
/******/ 							}
/******/ 							if (!options.ignoreErrored) {
/******/ 								if (!error) error = err;
/******/ 							}
/******/ 						}
/******/ 					}
/******/ 				}
/******/ 			}
/******/ 		}
/******/
/******/ 		// Load self accepted modules
/******/ 		for (i = 0; i < outdatedSelfAcceptedModules.length; i++) {
/******/ 			var item = outdatedSelfAcceptedModules[i];
/******/ 			moduleId = item.module;
/******/ 			hotCurrentParents = item.parents;
/******/ 			hotCurrentChildModule = moduleId;
/******/ 			try {
/******/ 				__webpack_require__(moduleId);
/******/ 			} catch (err) {
/******/ 				if (typeof item.errorHandler === "function") {
/******/ 					try {
/******/ 						item.errorHandler(err);
/******/ 					} catch (err2) {
/******/ 						if (options.onErrored) {
/******/ 							options.onErrored({
/******/ 								type: "self-accept-error-handler-errored",
/******/ 								moduleId: moduleId,
/******/ 								error: err2,
/******/ 								originalError: err
/******/ 							});
/******/ 						}
/******/ 						if (!options.ignoreErrored) {
/******/ 							if (!error) error = err2;
/******/ 						}
/******/ 						if (!error) error = err;
/******/ 					}
/******/ 				} else {
/******/ 					if (options.onErrored) {
/******/ 						options.onErrored({
/******/ 							type: "self-accept-errored",
/******/ 							moduleId: moduleId,
/******/ 							error: err
/******/ 						});
/******/ 					}
/******/ 					if (!options.ignoreErrored) {
/******/ 						if (!error) error = err;
/******/ 					}
/******/ 				}
/******/ 			}
/******/ 		}
/******/
/******/ 		// handle errors in accept handlers and self accepted module load
/******/ 		if (error) {
/******/ 			hotSetStatus("fail");
/******/ 			return Promise.reject(error);
/******/ 		}
/******/
/******/ 		if (hotQueuedInvalidatedModules) {
/******/ 			return hotApplyInternal(options).then(function(list) {
/******/ 				outdatedModules.forEach(function(moduleId) {
/******/ 					if (list.indexOf(moduleId) < 0) list.push(moduleId);
/******/ 				});
/******/ 				return list;
/******/ 			});
/******/ 		}
/******/
/******/ 		hotSetStatus("idle");
/******/ 		return new Promise(function(resolve) {
/******/ 			resolve(outdatedModules);
/******/ 		});
/******/ 	}
/******/
/******/ 	function hotApplyInvalidatedModules() {
/******/ 		if (hotQueuedInvalidatedModules) {
/******/ 			if (!hotUpdate) hotUpdate = {};
/******/ 			hotQueuedInvalidatedModules.forEach(hotApplyInvalidatedModule);
/******/ 			hotQueuedInvalidatedModules = undefined;
/******/ 			return true;
/******/ 		}
/******/ 	}
/******/
/******/ 	function hotApplyInvalidatedModule(moduleId) {
/******/ 		if (!Object.prototype.hasOwnProperty.call(hotUpdate, moduleId))
/******/ 			hotUpdate[moduleId] = modules[moduleId];
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
/******/ 			exports: {},
/******/ 			hot: hotCreateModule(moduleId),
/******/ 			parents: (hotCurrentParentsTemp = hotCurrentParents, hotCurrentParents = [], hotCurrentParentsTemp),
/******/ 			children: []
/******/ 		};
/******/
/******/ 		// Execute the module function
/******/ 		modules[moduleId].call(module.exports, module, module.exports, hotCreateRequire(moduleId));
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
/******/ 	__webpack_require__.p = "/static/";
/******/
/******/ 	// __webpack_hash__
/******/ 	__webpack_require__.h = function() { return hotCurrentHash; };
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
/******/ 	deferredModules.push([1,"vendor"]);
/******/ 	// run deferred modules when ready
/******/ 	return checkDeferredModules();
/******/ })
/************************************************************************/
/******/ ({

/***/ "./assets/react/DisclosureList.tsx":
/*!*****************************************!*\
  !*** ./assets/react/DisclosureList.tsx ***!
  \*****************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/extends */ "./node_modules/@babel/runtime/helpers/extends.js");
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/regenerator */ "./node_modules/@babel/runtime/regenerator/index.js");
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/helpers/asyncToGenerator */ "./node_modules/@babel/runtime/helpers/asyncToGenerator.js");
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var _fetch__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./_fetch */ "./assets/react/_fetch.ts");







var scrollToRef = function scrollToRef(ref) {
  window.scrollTo(0, ref.current.offsetTop);
};

var DisclosureList = function DisclosureList() {
  var _React$useState = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState([]),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState, 2),
      data = _React$useState2[0],
      setData = _React$useState2[1];

  var _React$useState3 = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState(""),
      _React$useState4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState3, 2),
      query = _React$useState4[0],
      setQuery = _React$useState4[1];

  var myRef = react__WEBPACK_IMPORTED_MODULE_4___default.a.useRef(null);

  var executeScroll = function executeScroll() {
    return scrollToRef(myRef);
  };

  var fetchData = /*#__PURE__*/function () {
    var _ref = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.mark(function _callee(query) {
      var response;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.wrap(function _callee$(_context) {
        while (1) {
          switch (_context.prev = _context.next) {
            case 0:
              _context.prev = 0;
              _context.next = 3;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_5__["appFetch"])("/api/rest/v3/financial-disclosures/?person__fullname=".concat(query));

            case 3:
              response = _context.sent;
              setQuery(query);
              setData(response['results']);
              console.log(response['results']);
              _context.next = 12;
              break;

            case 9:
              _context.prev = 9;
              _context.t0 = _context["catch"](0);
              console.log(_context.t0);

            case 12:
            case "end":
              return _context.stop();
          }
        }
      }, _callee, null, [[0, 9]]);
    }));

    return function fetchData(_x) {
      return _ref.apply(this, arguments);
    };
  }();

  function update(_ref2) {
    var data = _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, _ref2);

    var query = data.target.value;
    fetchData(query);
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, DisclosureHeader(executeScroll), DisclosureSearch(data, query, update), DisclosureFooter(myRef));
};

var DisclosureHeader = function DisclosureHeader(executeScroll) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h1", {
    className: "text-center"
  }, "Judicial Financial Disclosures Database"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
    className: "text-center gray large"
  }, "A collaboration of", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://demandprogress.org"
  }, " Demand Progress"), ",", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://fixthecourt.com"
  }, " Fix the Court"), ",", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://free.law"
  }, " Free Law Project"), ", and", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://muckrock.com"
  }, " MuckRock"), "."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
    className: "text-center"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    onClick: executeScroll,
    className: "btn btn-default"
  }, "Learn More")));
};

var DisclosureSearch = function DisclosureSearch(data, query, update) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "row v-offset-above-2"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "hidden-xs col-sm-1 col-md-2 col-lg-3"
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-xs-12 col-sm-10 col-md-8 col-lg-6 text-center form-group",
    id: "main-query-box"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("label", {
    className: "sr-only",
    htmlFor: "id_disclosures_filter"
  }, "Filter disclosures\u2026"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("input", {
    className: "form-control input-lg",
    name: "disclosures-filter",
    id: "id_disclosures_filter",
    autoComplete: "off",
    onChange: update,
    type: "text",
    placeholder: "Filter disclosures by typing a judge's name here\u2026"
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("table", {
    style: {
      "width": "100%"
    }
  }, query != "" ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tbody", null, data.map(function (row) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tr", {
      className: "col-xs-7 col-md-8 col-lg-12 tr-results"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", {
      className: "col-md-9"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      href: "/financial-disclosures/".concat(row.person.id, "/").concat(row.person.slug, "/?id=").concat(row.id)
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h4", {
      className: "text-left"
    }, "Judge ", row.person.name_first, " ", row.person.name_last)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
      className: "text-left"
    }, row.year)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", {
      className: "col-md-3"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      href: row.filepath
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("img", {
      src: row.thumbnail,
      alt: "Thumbnail of disclosure form",
      width: "100",
      height: "150",
      className: "img-responsive thumbnail shadow img-thumbnail"
    }))));
  })) : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tbody", null))))));
};

var DisclosureFooter = function DisclosureFooter(myRef) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "row v-offset-above-4 abcd",
    ref: myRef
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-xs-12 col-sm-6"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
    className: "lead"
  }, "Yadda Yadda Yadda"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, " Honestly this is where I think we could explain about collaborators?"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, "Our financial disclosure database is a collection of over 250,000 pages of financial records drawn from over 26,000 tiff and PDF files. We requested these files from the federal judiciary beginning in 2017 and have been gathering them since that time.")), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-xs-12 col-sm-6"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
    className: "lead"
  }, "The Data"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, "Financial Disclosures by federal judges is mandated by law. Starting int 1974 Judges have been required to make thier financial records available for 6 years. Beginning in 2017 we began requesting the financial records of every federal judge. "), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, "To learn more about how you can use API endpoints click this link."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://www.courtlistener.com/api/rest-info/#financialdisclosure-endpoint"
  }, "https://www.courtlistener.com/api/rest-info/#financialdisclosure-endpoint"))));
};

/* harmony default export */ __webpack_exports__["default"] = (DisclosureList);

/***/ }),

/***/ "./assets/react/DisclosureViewer.tsx":
/*!*******************************************!*\
  !*** ./assets/react/DisclosureViewer.tsx ***!
  \*******************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/extends */ "./node_modules/@babel/runtime/helpers/extends.js");
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/regenerator */ "./node_modules/@babel/runtime/regenerator/index.js");
/* harmony import */ var _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! @babel/runtime/helpers/asyncToGenerator */ "./node_modules/@babel/runtime/helpers/asyncToGenerator.js");
/* harmony import */ var _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var _fetch__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./_fetch */ "./assets/react/_fetch.ts");
/* harmony import */ var react_bootstrap__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! react-bootstrap */ "./node_modules/react-bootstrap/es/index.js");
/* harmony import */ var _disclosure_page_css__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./disclosure-page.css */ "./assets/react/disclosure-page.css");
/* harmony import */ var react_router_dom__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! react-router-dom */ "./node_modules/react-router-dom/esm/react-router-dom.js");
/* harmony import */ var _disclosure_models__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(/*! ./_disclosure_models */ "./assets/react/_disclosure_models.ts");
/* harmony import */ var _disclosure_helpers__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(/*! ./_disclosure_helpers */ "./assets/react/_disclosure_helpers.ts");












var TableNavigation = function TableNavigation(disclosures) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_4___default.a.Fragment, null, MainSection(disclosures));
};

var MainSection = function MainSection(disclosures) {
  var years = disclosures['years'].split(",");
  var doc_ids = disclosures['ids'].split(",");
  var is_admin = disclosures['admin'] == "True";
  var judge_name = disclosures['judge'];

  var _React$useState = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState(""),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState, 2),
      data = _React$useState2[0],
      setData = _React$useState2[1];

  var _React$useState3 = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState([]),
      _React$useState4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState3, 2),
      judge = _React$useState4[0],
      setJudge = _React$useState4[1];

  var _useParams = Object(react_router_dom__WEBPACK_IMPORTED_MODULE_8__["useParams"])(),
      judge_id = _useParams.judge_id;

  var year_index = Object(_disclosure_helpers__WEBPACK_IMPORTED_MODULE_10__["fetch_year_index"])(years, doc_ids);

  var _React$useState5 = react__WEBPACK_IMPORTED_MODULE_4___default.a.useState(year_index[0]),
      _React$useState6 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_React$useState5, 2),
      year = _React$useState6[0],
      setYear = _React$useState6[1];

  var fetchDisclosure = /*#__PURE__*/function () {
    var _ref = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.mark(function _callee(year, index) {
      var doc_id, response;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.wrap(function _callee$(_context) {
        while (1) {
          switch (_context.prev = _context.next) {
            case 0:
              _context.prev = 0;
              doc_id = doc_ids[index];
              _context.next = 4;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_5__["appFetch"])("/api/rest/v3/financial-disclosures/?person=".concat(judge_id, "&id=").concat(doc_id));

            case 4:
              response = _context.sent;
              setData(response['results'][0]);
              setYear(year);
              _context.next = 12;
              break;

            case 9:
              _context.prev = 9;
              _context.t0 = _context["catch"](0);
              console.log(_context.t0);

            case 12:
            case "end":
              return _context.stop();
          }
        }
      }, _callee, null, [[0, 9]]);
    }));

    return function fetchDisclosure(_x, _x2) {
      return _ref.apply(this, arguments);
    };
  }();

  var fetchJudge = /*#__PURE__*/function () {
    var _ref2 = _babel_runtime_helpers_asyncToGenerator__WEBPACK_IMPORTED_MODULE_2___default()( /*#__PURE__*/_babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.mark(function _callee2(query) {
      var response;
      return _babel_runtime_regenerator__WEBPACK_IMPORTED_MODULE_1___default.a.wrap(function _callee2$(_context2) {
        while (1) {
          switch (_context2.prev = _context2.next) {
            case 0:
              if (!(query == "")) {
                _context2.next = 4;
                break;
              }

              setJudge([]);
              _context2.next = 14;
              break;

            case 4:
              _context2.prev = 4;
              _context2.next = 7;
              return Object(_fetch__WEBPACK_IMPORTED_MODULE_5__["appFetch"])("/api/rest/v3/financial-disclosures/?person__fullname=".concat(query));

            case 7:
              response = _context2.sent;
              setJudge(response['results']);
              _context2.next = 14;
              break;

            case 11:
              _context2.prev = 11;
              _context2.t0 = _context2["catch"](4);
              setJudge([]);

            case 14:
            case "end":
              return _context2.stop();
          }
        }
      }, _callee2, null, [[4, 11]]);
    }));

    return function fetchJudge(_x3) {
      return _ref2.apply(this, arguments);
    };
  }();

  if (data == '') {
    fetchDisclosure(year, year_index[1]);
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, data != "" && data.has_been_extracted == true ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-3 v-offset-above-3"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-lg-9"
  }, Tabs(data, years, year, fetchDisclosure, doc_ids, judge_name), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "tabcontent"
  }, TableMaker(data, "investments", is_admin), TableMaker(data, "gifts", is_admin), TableMaker(data, "reimbursements", is_admin), TableMaker(data, "spouse_incomes", is_admin), TableMaker(data, "debts", is_admin), TableMaker(data, "non_investment_incomes", is_admin), TableMaker(data, "agreements", is_admin), TableMaker(data, "positions", is_admin), data.addendum_content_raw != "" ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_4___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, "Addendum"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("article", null, data.addendum_content_raw), " ") : "")), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-lg-3"
  }, Sidebar(data, is_admin, judge, fetchJudge)))) : data.has_been_extracted == false ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-3 v-offset-above-3"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-lg-9"
  }, Tabs(data, years, year, fetchDisclosure, doc_ids, judge_name), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "tabcontent"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "text-center v-offset-above-4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-exclamation-triangle gray"
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h1", null, "Table extraction failed."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, "You can still view this Financial Disclosure by clicking the thumbnail.")))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "col-lg-3"
  }, Sidebar(data, is_admin, judge, fetchJudge)))) : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "row"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", {
    className: "text-center"
  }, " Loading ...")));
};

var TableMaker = function TableMaker(data, key, is_admin) {
  var url = data.filepath;
  var disclosure_id = data.id;
  var rows = data[key];
  var fields = _disclosure_models__WEBPACK_IMPORTED_MODULE_9__["disclosureModel"][key]['fields'];
  var title = _disclosure_models__WEBPACK_IMPORTED_MODULE_9__["disclosureModel"][key]['title'];
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, rows.length > 0 ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "table-responsive"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, title, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "/api/rest/v3/".concat(key.replaceAll("_", "-"), "/?financial_disclosure__id=").concat(disclosure_id)
  }, " ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-code gray pull-right"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["Table"], {
    striped: true,
    bordered: true,
    hover: true,
    responsive: true
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("thead", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tr", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("th", {
    key: ""
  }, " "), is_admin == true ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("th", null, "Admin") : "", Object.entries(fields).map(function (_ref3) {
    var _ref4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_ref3, 2),
        key = _ref4[0],
        value = _ref4[1];

    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("th", {
      key: value
    }, key);
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tbody", null, rows.sort(function (x, y) {
    return x.id > y.id ? 1 : -1;
  }).map(function (entry) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tr", {
      key: entry.id,
      className: ""
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      title: "Go to PDF",
      href: url + "#page=" + entry.page_number
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
      className: "fa fa-file-text-o gray"
    })), "\xA0", entry.redacted == true ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
      title: "Redaction present in row",
      className: "fa fa-file-excel-o black"
    }) : ""), is_admin == true ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      href: "/admin/disclosures/".concat(key.replaceAll("_", "").slice(0, -1), "/").concat(entry.id, "/")
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
      className: "fa fa-pencil gray"
    }))) : "", Object.entries(fields).map(function (_ref5) {
      var _ref6 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_3___default()(_ref5, 2),
          key = _ref6[0],
          value = _ref6[1];

      return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", null, Object(_disclosure_helpers__WEBPACK_IMPORTED_MODULE_10__["convertTD"])(entry[value], title, value), entry[value] == -1 ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
        className: "fa fa-eye-slash black"
      }) : "");
    }));
  })))) : "");
};

var Support = function Support() {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    id: "support"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "Support FLP ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-heart-o red"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
    className: "v-offset-above-1"
  }, "CourtListener is a project of ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "https://free.law",
    target: "_blank"
  }, "Free Law Project"), ", a federally-recognized 501(c)(3) non-profit. We rely on donations for our financial security."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, "Please support our work with a donation."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "",
    className: "btn btn-danger btn-lg btn-block"
  }, "Donate Now")));
};

var Thumb = function Thumb(data) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "Download ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-download gray"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("hr", null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: data.filepath
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("img", {
    src: data.thumbnail,
    alt: "Thumbnail of disclosure form",
    width: "200",
    className: "img-responsive thumbnail shadow img-thumbnail img-rounded"
  })));
};

var Sidebar = function Sidebar(data, is_admin, judge, fetchJudge) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, is_admin == true ? AdminPanel(data) : "", Thumb(data), Notes(), SearchPanel(judge, fetchJudge), Support());
};

var Notes = function Notes() {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "Notes ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-sticky-note-o"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("hr", null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "The data in this file was extracted with OCR technology and may contain typos."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("ul", {
    className: "v-offset-above-2 v-offset-below-2"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("li", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-file-text-o gray"
  }), " Links to the PDF row (if possible)."), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("li", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-file-excel-o black"
  }), " The row may contain a redaction"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("li", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-eye-slash black"
  }), " Indicates the OCR identified data in the row but could not extract it")));
};

var SearchPanel = function SearchPanel(judge, fetchJudge) {
  function update(_ref7) {
    var data = _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, _ref7);

    var query = data.target.value;
    fetchJudge(query);
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-4 "
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "Search ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-search gray"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("hr", null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("input", {
    onChange: update,
    className: "form-control input-sm",
    placeholder: "Filter disclosures by typing a judge's name here…"
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("br", null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("table", {
    className: "search-panel-table"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tbody", null, judge.map(function (row) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("tr", {
      key: row.id
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("td", {
      className: "search-panel-td"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      href: "/financial-disclosures/".concat(row.person.id, "/").concat(row.person.slug, "/?id=").concat(row.id)
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h4", {
      className: "text-left"
    }, "Judge ", row.person.name_first, " ", row.person.name_last)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("p", {
      className: "text-left"
    }, row.year)));
  }))));
};

var AdminPanel = function AdminPanel(data) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", {
    className: "v-offset-below-4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h3", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "Admin ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
    className: "fa fa-key red"
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("hr", null), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("span", null, "If Admin provide special links to things"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: "/admin/disclosures/financialdisclosure/".concat(data.id, "/")
  }, "Admin Page"));
};

var Tabs = function Tabs(data, years, year, fetchDisclosure, doc_ids, judge_name) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("h1", {
    className: "text-center"
  }, "Financial Disclosures for J.\xA0", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
    href: window.location.pathname.replace("financial-disclosures", "person")
  }, judge_name)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("ul", {
    className: "nav nav-tabs v-offset-below-2 v-offset-above-3",
    role: ""
  }, years.map(function (yr, index) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("li", {
      className: year == yr ? "active" : "",
      role: "presentation"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("a", {
      href: "?id=".concat(doc_ids[index]),
      onClick: function onClick() {
        fetchDisclosure(yr, index);
      }
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_4___default.a.createElement("i", {
      className: "fa fa-file-text-o gray"
    }), "\xA0 ", yr));
  })));
};

/* harmony default export */ __webpack_exports__["default"] = (TableNavigation);

/***/ }),

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

  function go_to(e) {
    window.location.href = "/tags/".concat(user, "/").concat(name, "/");
    e.preventDefault();
    e.stopPropagation();
  }

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
    onClick: function onClick(e) {
      return go_to(e);
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

  var _useQuery = Object(react_query__WEBPACK_IMPORTED_MODULE_4__["useQuery"])(['tags', page], getTags, {
    keepPreviousData: true
  }),
      isLoading = _useQuery.isLoading,
      isError = _useQuery.isError,
      error = _useQuery.error,
      data = _useQuery.data,
      isFetching = _useQuery.isFetching;

  var latestData = data;

  if (latestData == undefined) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Loading...");
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, isPageOwner ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("h1", null, "Your Tags") : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("h1", null, "Tags for: ", userName), isLoading ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Loading...") : isFetching ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Loading...") : isError ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement("div", null, "Error: ", error.message, " ") : /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_3___default.a.createElement(_TagListInner__WEBPACK_IMPORTED_MODULE_5__["default"], {
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
/* harmony import */ var date_fns_format__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! date-fns/format */ "./node_modules/date-fns/esm/format/index.js");
/* harmony import */ var date_fns_parseISO__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! date-fns/parseISO */ "./node_modules/date-fns/esm/parseISO/index.js");
/* harmony import */ var react_bootstrap_lib_Button__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! react-bootstrap/lib/Button */ "./node_modules/react-bootstrap/lib/Button.js");
/* harmony import */ var react_bootstrap_lib_Button__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(react_bootstrap_lib_Button__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var react_input_switch__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! react-input-switch */ "./node_modules/react-input-switch/dist/index.esm.js");
/* harmony import */ var _useTags__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./_useTags */ "./assets/react/_useTags.ts");








var Toggle = function Toggle(_ref) {
  var state = _ref.state,
      name = _ref.name,
      id = _ref.id;

  var _updateTags = Object(_useTags__WEBPACK_IMPORTED_MODULE_6__["updateTags"])(),
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

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_input_switch__WEBPACK_IMPORTED_MODULE_5__["default"], {
    className: 'toggle',
    value: value,
    onChange: trigger_state_change
  });
};

var TagListInner = function TagListInner(_ref2) {
  var data = _ref2.data,
      isPageOwner = _ref2.isPageOwner,
      userName = _ref2.userName;

  var _updateTags2 = Object(_useTags__WEBPACK_IMPORTED_MODULE_6__["updateTags"])(),
      modifyTags = _updateTags2.modifyTags,
      deleteTags = _updateTags2.deleteTags;

  var _React$useState = react__WEBPACK_IMPORTED_MODULE_1___default.a.useState(data),
      _React$useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_0___default()(_React$useState, 2),
      rows = _React$useState2[0],
      setRows = _React$useState2[1];

  var delete_tag = function delete_tag(e, tag_id) {
    if (window.confirm('Are you sure you want to delete this item?')) {
      deleteTags(tag_id);
      var index = data.findIndex(function (x) {
        return x.id === tag_id;
      });
      data.splice(index, 1);
      setRows(data);
    }
  };

  var onRowClick = function onRowClick(e, name) {
    if (e.metaKey || e.ctrlKey) {
      window.open("/tags/".concat(userName, "/").concat(name, "/"));
    } else {
      window.location.href = "/tags/".concat(userName, "/").concat(name, "/");
    }
  };

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("div", {
    className: "table-responsive"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("table", {
    className: "table settings-table tablesorter-bootstrap"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("thead", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tr", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Name"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Created"), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Views"), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Public"), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("th", null, "Delete"))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tbody", null, rows.map(function (tag) {
    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("tr", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        cursor: 'pointer'
      },
      onClick: function onClick(event) {
        return onRowClick(event, tag.name);
      }
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("span", {
      className: "tag"
    }, tag.name)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        cursor: 'pointer'
      },
      onClick: function onClick(event) {
        return onRowClick(event, tag.name);
      }
    }, Object(date_fns_format__WEBPACK_IMPORTED_MODULE_2__["default"])(Object(date_fns_parseISO__WEBPACK_IMPORTED_MODULE_3__["default"])(tag.date_created || ''), 'MMM d, yyyy')), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", {
      style: {
        cursor: 'pointer'
      },
      onClick: function onClick(event) {
        return onRowClick(event, tag.name);
      }
    }, tag.view_count), isPageOwner && /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_1___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(Toggle, {
      id: tag.id,
      name: tag.name,
      state: tag.published
    })), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement("td", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_1___default.a.createElement(react_bootstrap_lib_Button__WEBPACK_IMPORTED_MODULE_4___default.a, {
      id: "dlt_".concat(tag.id),
      onClick: function onClick(event) {
        return delete_tag(event, Number("".concat(tag.id)));
      },
      className: 'fa fa-trash btn-sm inline delete-tag'
    }, ' ', "Delete"))));
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
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! @babel/runtime/helpers/extends */ "./node_modules/@babel/runtime/helpers/extends.js");
/* harmony import */ var _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! @babel/runtime/helpers/slicedToArray */ "./node_modules/@babel/runtime/helpers/slicedToArray.js");
/* harmony import */ var _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1___default = /*#__PURE__*/__webpack_require__.n(_babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1__);
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_2__ = __webpack_require__(/*! react */ "./node_modules/react/index.js");
/* harmony import */ var react__WEBPACK_IMPORTED_MODULE_2___default = /*#__PURE__*/__webpack_require__.n(react__WEBPACK_IMPORTED_MODULE_2__);
/* harmony import */ var react_showdown__WEBPACK_IMPORTED_MODULE_3__ = __webpack_require__(/*! react-showdown */ "./node_modules/react-showdown/dist/react-showdown.esm.js");
/* harmony import */ var showdown__WEBPACK_IMPORTED_MODULE_4__ = __webpack_require__(/*! showdown */ "./node_modules/showdown/dist/showdown.js");
/* harmony import */ var showdown__WEBPACK_IMPORTED_MODULE_4___default = /*#__PURE__*/__webpack_require__.n(showdown__WEBPACK_IMPORTED_MODULE_4__);
/* harmony import */ var _useTags__WEBPACK_IMPORTED_MODULE_5__ = __webpack_require__(/*! ./_useTags */ "./assets/react/_useTags.ts");
/* harmony import */ var react_bootstrap__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! react-bootstrap */ "./node_modules/react-bootstrap/es/index.js");
/* harmony import */ var _tag_page_css__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./tag-page.css */ "./assets/react/tag-page.css");
/* harmony import */ var react_input_switch__WEBPACK_IMPORTED_MODULE_8__ = __webpack_require__(/*! react-input-switch */ "./node_modules/react-input-switch/dist/index.esm.js");
/* harmony import */ var react_markdown_editor_lite__WEBPACK_IMPORTED_MODULE_9__ = __webpack_require__(/*! react-markdown-editor-lite */ "./node_modules/react-markdown-editor-lite/lib/index.js");
/* harmony import */ var react_markdown_editor_lite__WEBPACK_IMPORTED_MODULE_9___default = /*#__PURE__*/__webpack_require__.n(react_markdown_editor_lite__WEBPACK_IMPORTED_MODULE_9__);
/* harmony import */ var react_markdown_editor_lite_lib_index_css__WEBPACK_IMPORTED_MODULE_10__ = __webpack_require__(/*! react-markdown-editor-lite/lib/index.css */ "./node_modules/react-markdown-editor-lite/lib/index.css");












var PageTop = function PageTop(data) {
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react__WEBPACK_IMPORTED_MODULE_2___default.a.Fragment, null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", {
    className: "row"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", {
    className: "col-md-2"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("h1", {
    className: "clearfix"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("span", {
    className: "tag"
  }, data.name)))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("p", null, "Created by", ' ', /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("a", {
    className: "alt tag-back",
    href: "/tags/".concat(data.user, "/")
  }, data.user), ' ', "on ", /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("span", {
    className: "alt"
  }, data.dateCreatedDate), " with", ' ', /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("span", {
    className: "alt"
  }, data.viewCount.toLocaleString()), " view", data.viewCount !== 1 ? 's' : ''));
};

var TagOptions = function TagOptions(data) {
  var _updateTags = Object(_useTags__WEBPACK_IMPORTED_MODULE_5__["updateTags"])(),
      modifyTags = _updateTags.modifyTags,
      deleteTags = _updateTags.deleteTags;

  var _useState = Object(react__WEBPACK_IMPORTED_MODULE_2__["useState"])(data.published == 'True'),
      _useState2 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1___default()(_useState, 2),
      isPublic = _useState2[0],
      setPublic = _useState2[1];

  var delete_tag = function delete_tag(tag_id) {
    if (window.confirm('Are you sure you want to delete this item?')) {
      deleteTags(tag_id); // Relocate to the previous page on delete

      var url = window.location.href.slice(0, -1);
      window.location.href = url.substr(0, url.lastIndexOf('/') + 1);
    }
  };

  function toggle_menu(published, name, id) {
    modifyTags({
      published: !published,
      name: name,
      id: id
    });
    setPublic(!published);
  }

  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", {
    id: 'tag-settings-parent',
    className: "float-right v-offset-above-1"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["ButtonToolbar"], null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["DropdownButton"], {
    pullRight: true,
    className: 'fa fa-gear gray',
    bsSize: "large",
    noCaret: true,
    title: "",
    id: "tag-settings"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("li", {
    role: "presentation",
    value: +isPublic,
    onClick: function onClick(e) {
      return toggle_menu(isPublic, "".concat(data.name), Number("".concat(data.id)));
    },
    className: ""
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("a", {
    role: "menuitem",
    href: "#"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_input_switch__WEBPACK_IMPORTED_MODULE_8__["default"], {
    value: +isPublic
  }), "\xA0Publicly Available")), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["MenuItem"], {
    divider: true
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["MenuItem"], {
    checked: true,
    onClick: function onClick(_) {
      return delete_tag(Number("".concat(data.id)));
    },
    eventKey: "4"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("i", {
    className: "fa fa-trash fa-fw gray"
  }), "\xA0Delete"), data.adminUrl ? /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["MenuItem"], {
    href: data.adminUrl
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("i", {
    className: "fa fa-lock fa-fw gray"
  }), "\xA0Admin") : ''))));
};

var TagMarkdown = function TagMarkdown(data) {
  var _updateTags2 = Object(_useTags__WEBPACK_IMPORTED_MODULE_5__["updateTags"])(),
      modifyTags = _updateTags2.modifyTags,
      deleteTags = _updateTags2.deleteTags;

  var _useState3 = Object(react__WEBPACK_IMPORTED_MODULE_2__["useState"])(data.description),
      _useState4 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1___default()(_useState3, 2),
      text = _useState4[0],
      setText = _useState4[1];

  var _useState5 = Object(react__WEBPACK_IMPORTED_MODULE_2__["useState"])('write'),
      _useState6 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1___default()(_useState5, 2),
      key = _useState6[0],
      setKey = _useState6[1];

  var _useState7 = Object(react__WEBPACK_IMPORTED_MODULE_2__["useState"])(true),
      _useState8 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_1___default()(_useState7, 2),
      disabled = _useState8[0],
      setDisabled = _useState8[1];

  function save_on_select(k) {
    if (k !== key) {
      if (k == 'write') {
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

  function update(_ref) {
    var data = _babel_runtime_helpers_extends__WEBPACK_IMPORTED_MODULE_0___default()({}, _ref);

    setText(data.text);
    setDisabled(false);
  }

  if (data.pageOwner == 'False') {
    if (text == '') {
      return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(PageTop, data));
    }

    return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(PageTop, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", {
      id: "markdown_viewer",
      className: "col-12 view-only"
    }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_showdown__WEBPACK_IMPORTED_MODULE_3__["default"], {
      markdown: text || '',
      flavor: 'github',
      options: {
        tables: true,
        emoji: true,
        simpleLineBreaks: true
      }
    })));
  }

  var convert = new showdown__WEBPACK_IMPORTED_MODULE_4__["Converter"]({
    tables: true,
    emoji: true,
    simpleLineBreaks: true
  });
  return /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", null, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(TagOptions, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(PageTop, data), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["TabContainer"], {
    id: "tab-tabs",
    defaultActiveKey: "first"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["Tabs"], {
    id: "controlled-tab-example",
    activeKey: key,
    onSelect: save_on_select
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["Tab"], {
    eventKey: "write",
    title: "Notes"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("div", {
    id: "markdown_viewer",
    className: "col-12"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_showdown__WEBPACK_IMPORTED_MODULE_3__["default"], {
    markdown: text || '',
    flavor: 'github',
    options: {
      tables: true,
      emoji: true,
      simpleLineBreaks: true
    }
  }))), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["Tab"], {
    eventKey: "preview",
    title: "Edit"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_markdown_editor_lite__WEBPACK_IMPORTED_MODULE_9___default.a, {
    value: text,
    onChange: update,
    style: {
      height: '500px'
    },
    plugins: ['header', 'font-bold', 'font-italic', 'font-underline', 'font-strikethrough', 'list-unordered', 'list-ordered', 'block-quote', 'block-wrap', 'block-code-block', 'block-code-inline', 'mode-toggle', 'logger', 'table', 'link', 'auto-resize', 'tab-insert'],
    renderHTML: function renderHTML(text) {
      return convert.makeHtml(text);
    }
  }), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("span", {
    id: 'save_span',
    style: {
      "float": 'right'
    }
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement(react_bootstrap__WEBPACK_IMPORTED_MODULE_6__["Button"], {
    disabled: disabled,
    id: 'save_button',
    onClick: save_button,
    className: 'whitesmoke'
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_2___default.a.createElement("i", {
    className: 'fa fa-save'
  }), " Save"))))));
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





function _createForOfIteratorHelper(o, allowArrayLike) { var it; if (typeof Symbol === "undefined" || o[Symbol.iterator] == null) { if (Array.isArray(o) || (it = _unsupportedIterableToArray(o)) || allowArrayLike && o && typeof o.length === "number") { if (it) o = it; var i = 0; var F = function F() {}; return { s: F, n: function n() { if (i >= o.length) return { done: true }; return { done: false, value: o[i++] }; }, e: function e(_e) { throw _e; }, f: F }; } throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method."); } var normalCompletion = true, didErr = false, err; return { s: function s() { it = o[Symbol.iterator](); }, n: function n() { var step = it.next(); normalCompletion = step.done; return step; }, e: function e(_e2) { didErr = true; err = _e2; }, f: function f() { try { if (!normalCompletion && it["return"] != null) it["return"](); } finally { if (didErr) throw err; } } }; }

function _unsupportedIterableToArray(o, minLen) { if (!o) return; if (typeof o === "string") return _arrayLikeToArray(o, minLen); var n = Object.prototype.toString.call(o).slice(8, -1); if (n === "Object" && o.constructor) n = o.constructor.name; if (n === "Map" || n === "Set") return Array.from(o); if (n === "Arguments" || /^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(n)) return _arrayLikeToArray(o, minLen); }

function _arrayLikeToArray(arr, len) { if (len == null || len > arr.length) len = arr.length; for (var i = 0, arr2 = new Array(len); i < len; i++) { arr2[i] = arr[i]; } return arr2; }

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
  }); // fetch more if we are at the bottom of the list

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
          return _objectSpread(_objectSpread({}, changes), {}, {
            isOpen: true,
            highlightedIndex: state.highlightedIndex,
            inputValue: 'return'
          });

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
    onIsOpenChange: function onIsOpenChange(inputId) {
      if (!isOpen) {
        document.getElementById(getInputProps()['id']).focus();
      }
    },
    onInputValueChange: function onInputValueChange(_ref2) {
      var inputValue = _ref2.inputValue;
      if (inputValue !== 'return') return;
      var first_item = document.querySelector('a.list-group-item > p');

      if (!first_item) {
        var rows = document.querySelectorAll('input.form-check');

        var _iterator = _createForOfIteratorHelper(rows),
            _step;

        try {
          for (_iterator.s(); !(_step = _iterator.n()).done;) {
            var idx = _step.value;
            var name = document.getElementById(getInputProps()['id']).value;

            if (idx.value == name) {
              (function () {
                var tag_id = Number(idx.getAttribute('data-tagid'));
                var assoc_id = Number(idx.id);
                var isAlreadySelected = !associations ? false : !!associations.find(function (a) {
                  return a.tag === tag_id;
                });

                if (isAlreadySelected) {
                  console.log("Removing ".concat(name, " from tags for docket ").concat(docket));
                  deleteAssociation({
                    assocId: assoc_id
                  });
                } else {
                  console.log("Adding ".concat(name, " to tags for docket ").concat(docket));
                  addNewAssociation({
                    tag: tag_id
                  });
                }
              })();
            }
          }
        } catch (err) {
          _iterator.e(err);
        } finally {
          _iterator.f();
        }

        return;
      }

      var d3i0 = first_item.textContent || '';
      var isCreateItemOption = d3i0.startsWith('Create Tag:');

      if (isCreateItemOption) {
        var validInput = textVal.match(/^[a-z0-9-]*$/);

        if (!validInput) {
          return setValidationError("Only lowercase letters, numbers, and '-' allowed");
        }

        return addNewTag({
          name: textVal
        });
      }
    },
    onSelectedItemChange: function onSelectedItemChange(_ref3) {
      var selectedItem = _ref3.selectedItem;
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
    onHighlightedIndexChange: function onHighlightedIndexChange(_ref4) {
      var highlightedIndex = _ref4.highlightedIndex;

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


  var disableDownshiftMenuToggle = function disableDownshiftMenuToggle(_ref5) {
    var nativeEvent = _ref5.nativeEvent;
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
      position: 'absolute',
      display: isOpen ? 'block' : 'none'
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
  }), "View All Tags")));
};

/* harmony default export */ __webpack_exports__["default"] = (TagSelect);

/***/ }),

/***/ "./assets/react/_disclosure_helpers.ts":
/*!*********************************************!*\
  !*** ./assets/react/_disclosure_helpers.ts ***!
  \*********************************************/
/*! exports provided: convertTD, fetch_year_index */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "convertTD", function() { return convertTD; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "fetch_year_index", function() { return fetch_year_index; });
/* harmony import */ var _disclosure_models__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ./_disclosure_models */ "./assets/react/_disclosure_models.ts");

var convertTD = function convertTD(value, table, key) {
  if (value == -1) {
    return "";
  }

  if (table == "Investments" && key == "transaction_value_code" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["GROSS_VALUE"][value], " (").concat(value, ")");
  }

  if (table == "Debts" && key == "value_code" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["GROSS_VALUE"][value], " (").concat(value, ")");
  }

  if (table == "Investments" && key == "income_during_reporting_period_code" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["INCOME_GAIN"][value], " (").concat(value, ")");
  }

  if (table == "Investments" && key == "gross_value_method" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["VALUATION_METHODS"][value], " (").concat(value, ")");
  }

  if (table == "Investments" && key == "gross_value_code" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["GROSS_VALUE"][value], " (").concat(value, ")");
  }

  if (table == "Investments" && key == "transaction_gain_code" && value) {
    return "".concat(_disclosure_models__WEBPACK_IMPORTED_MODULE_0__["INCOME_GAIN"][value], " (").concat(value, ")");
  }

  return value;
};

var getIndex = function getIndex(value, arr) {
  for (var i = 0; i < arr.length; i++) {
    if (arr[i] === value.toString()) {
      return i;
    }
  }

  return 0;
};

var fetch_year_index = function fetch_year_index(years, doc_ids) {
  var search = window.location.search;
  var params = new URLSearchParams(search);
  var optional_doc_id = params.get('id');
  var index = 0;

  if (optional_doc_id != null) {
    index = getIndex(optional_doc_id, doc_ids);
  }

  return [years[index], index];
};

/***/ }),

/***/ "./assets/react/_disclosure_models.ts":
/*!********************************************!*\
  !*** ./assets/react/_disclosure_models.ts ***!
  \********************************************/
/*! exports provided: INCOME_GAIN, GROSS_VALUE, VALUATION_METHODS, disclosureModel */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "INCOME_GAIN", function() { return INCOME_GAIN; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "GROSS_VALUE", function() { return GROSS_VALUE; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "VALUATION_METHODS", function() { return VALUATION_METHODS; });
/* harmony export (binding) */ __webpack_require__.d(__webpack_exports__, "disclosureModel", function() { return disclosureModel; });
var INCOME_GAIN = {
  "A": "1‑1,000",
  "B": "1,001‑2,500",
  "C": "2,501‑5,000",
  "D": "5,001‑15,000",
  "E": "15,001‑50,000",
  "F": "50,001‑100,000",
  "G": "100,001‑1,000,000",
  "H1": "1,000,001‑5,000,000",
  "H2": "5,000,001+",
  "-1": "Failed Extraction"
};
var GROSS_VALUE = {
  "J": "1‑15,000",
  "K": "15,001‑50,000",
  "L": "50,001‑100,000",
  "M": "100,001‑250,000",
  "N": "250,001‑500,000",
  "O": "500,001‑1,000,000",
  "P1": "1,000,001‑5,000,000",
  "P2": "5,000,001‑25,000,000",
  "P3": "25,000,001‑50,000,000",
  "P4": "50,000,00+",
  "-1": "Failed Extraction"
};
var VALUATION_METHODS = {
  "Q": "Appraisal",
  "R": "Cost (Real Estate Only)",
  "S": "Assessment",
  "T": "Cash Market",
  "U": "Book Value",
  "V": "Other",
  "W": "Estimated",
  "-1": "Failed Extraction"
};
var investmentFields = {
  "Description": "description",
  "Gross Val. Code": "gross_value_code",
  "Gross Val. Method": "gross_value_method",
  "Income Code": "income_during_reporting_period_code",
  "Income Type": "income_during_reporting_period_type",
  "Trans. Date": "transaction_date_raw",
  "Trans. Value": "transaction_value_code",
  "Trans. Gain": "transaction_gain_code",
  "Trans. Partner": "transaction_partner"
};
var giftFields = {
  "Source": "source",
  "Value": "value",
  "Description": "description"
};
var reimbursementsFields = {
  "Dates": "date_raw",
  "Location": "location",
  "Source": "source",
  "Purpose": "purpose",
  "Items": "items_paid_or_provided"
};
var noninvestmentFields = {
  "Dates": "date_raw",
  "Source": "source_type",
  "Income Amount": "income_amount"
};
var agreementFields = {
  "Dates": "date_raw",
  "Source": "parties_and_terms",
  "Income Amount": "parties_and_terms"
};
var positionFields = {
  "Position": "position",
  "Organization": "organization_name"
};
var debtFields = {
  "Creditor Name": "creditor_name",
  "Description": "description",
  "Value Code": "value_code"
};
var spouseFields = {
  "Date": "date_raw",
  "Location": "source_type"
};
var disclosureModel = {
  "investments": {
    "fields": investmentFields,
    "title": "Investments"
  },
  "gifts": {
    "fields": giftFields,
    "title": "Gifts"
  },
  "debts": {
    "fields": debtFields,
    "title": "Debts"
  },
  "positions": {
    "fields": positionFields,
    "title": "Positions"
  },
  "spouse_incomes": {
    "fields": spouseFields,
    "title": "Spousal Income"
  },
  "agreements": {
    "fields": agreementFields,
    "title": "Agreements"
  },
  "non_investment_incomes": {
    "fields": noninvestmentFields,
    "title": "Non Investment Income"
  },
  "reimbursements": {
    "fields": reimbursementsFields,
    "title": "Reimbursements"
  }
};

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
    enabled: enabled,
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
    onSuccess: function onSuccess(data, variables) {}
  }),
      _useMutation8 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation7, 1),
      deleteTags = _useMutation8[0];

  var _useMutation9 = Object(react_query__WEBPACK_IMPORTED_MODULE_6__["useMutation"])(updateTag, {
    // To update a description or publication status
    onSuccess: function onSuccess(data, variables) {}
  }),
      _useMutation10 = _babel_runtime_helpers_slicedToArray__WEBPACK_IMPORTED_MODULE_4___default()(_useMutation9, 1),
      modifyTags = _useMutation10[0];

  return {
    modifyTags: modifyTags,
    deleteTags: deleteTags
  };
};

/***/ }),

/***/ "./assets/react/disclosure-page.css":
/*!******************************************!*\
  !*** ./assets/react/disclosure-page.css ***!
  \******************************************/
/*! exports provided: default */
/***/ (function(module, __webpack_exports__, __webpack_require__) {

"use strict";
__webpack_require__.r(__webpack_exports__);
/* harmony import */ var _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0__ = __webpack_require__(/*! ../../node_modules/style-loader/dist/runtime/injectStylesIntoStyleTag.js */ "./node_modules/style-loader/dist/runtime/injectStylesIntoStyleTag.js");
/* harmony import */ var _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0___default = /*#__PURE__*/__webpack_require__.n(_node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0__);
/* harmony import */ var _node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! !../../node_modules/css-loader/dist/cjs.js!./disclosure-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/disclosure-page.css");

            

var options = {};

options.insert = "head";
options.singleton = false;

var update = _node_modules_style_loader_dist_runtime_injectStylesIntoStyleTag_js__WEBPACK_IMPORTED_MODULE_0___default()(_node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"], options);


if (true) {
  if (!_node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals || module.hot.invalidate) {
    var isEqualLocals = function isEqualLocals(a, b, isNamedExport) {
  if (!a && b || a && !b) {
    return false;
  }

  var p;

  for (p in a) {
    if (isNamedExport && p === 'default') {
      // eslint-disable-next-line no-continue
      continue;
    }

    if (a[p] !== b[p]) {
      return false;
    }
  }

  for (p in b) {
    if (isNamedExport && p === 'default') {
      // eslint-disable-next-line no-continue
      continue;
    }

    if (!a[p]) {
      return false;
    }
  }

  return true;
};
    var oldLocals = _node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals;

    module.hot.accept(
      /*! !../../node_modules/css-loader/dist/cjs.js!./disclosure-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/disclosure-page.css",
      function(__WEBPACK_OUTDATED_DEPENDENCIES__) { /* harmony import */ _node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! !../../node_modules/css-loader/dist/cjs.js!./disclosure-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/disclosure-page.css");
(function () {
        if (!isEqualLocals(oldLocals, _node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals, undefined)) {
                module.hot.invalidate();

                return;
              }

              oldLocals = _node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals;

              update(_node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"]);
      })(__WEBPACK_OUTDATED_DEPENDENCIES__); }.bind(this)
    )
  }

  module.hot.dispose(function() {
    update();
  });
}

/* harmony default export */ __webpack_exports__["default"] = (_node_modules_css_loader_dist_cjs_js_disclosure_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals || {});

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
/* harmony import */ var _DisclosureList__WEBPACK_IMPORTED_MODULE_6__ = __webpack_require__(/*! ./DisclosureList */ "./assets/react/DisclosureList.tsx");
/* harmony import */ var _DisclosureViewer__WEBPACK_IMPORTED_MODULE_7__ = __webpack_require__(/*! ./DisclosureViewer */ "./assets/react/DisclosureViewer.tsx");









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
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_TagPage__WEBPACK_IMPORTED_MODULE_5__["TagMarkdown"], data)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Route"], {
    exact: true,
    path: "/financial-disclosures/"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_DisclosureList__WEBPACK_IMPORTED_MODULE_6__["default"], data)), /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(react_router_dom__WEBPACK_IMPORTED_MODULE_2__["Route"], {
    path: "/financial-disclosures/:judge_id/:slug/"
  }, /*#__PURE__*/react__WEBPACK_IMPORTED_MODULE_0___default.a.createElement(_DisclosureViewer__WEBPACK_IMPORTED_MODULE_7__["default"], data))));
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


if (true) {
  if (!_node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals || module.hot.invalidate) {
    var isEqualLocals = function isEqualLocals(a, b, isNamedExport) {
  if (!a && b || a && !b) {
    return false;
  }

  var p;

  for (p in a) {
    if (isNamedExport && p === 'default') {
      // eslint-disable-next-line no-continue
      continue;
    }

    if (a[p] !== b[p]) {
      return false;
    }
  }

  for (p in b) {
    if (isNamedExport && p === 'default') {
      // eslint-disable-next-line no-continue
      continue;
    }

    if (!a[p]) {
      return false;
    }
  }

  return true;
};
    var oldLocals = _node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals;

    module.hot.accept(
      /*! !../../node_modules/css-loader/dist/cjs.js!./tag-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/tag-page.css",
      function(__WEBPACK_OUTDATED_DEPENDENCIES__) { /* harmony import */ _node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__ = __webpack_require__(/*! !../../node_modules/css-loader/dist/cjs.js!./tag-page.css */ "./node_modules/css-loader/dist/cjs.js!./assets/react/tag-page.css");
(function () {
        if (!isEqualLocals(oldLocals, _node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals, undefined)) {
                module.hot.invalidate();

                return;
              }

              oldLocals = _node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals;

              update(_node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"]);
      })(__WEBPACK_OUTDATED_DEPENDENCIES__); }.bind(this)
    )
  }

  module.hot.dispose(function() {
    update();
  });
}

/* harmony default export */ __webpack_exports__["default"] = (_node_modules_css_loader_dist_cjs_js_tag_page_css__WEBPACK_IMPORTED_MODULE_1__["default"].locals || {});

/***/ }),

/***/ "./node_modules/css-loader/dist/cjs.js!./assets/react/disclosure-page.css":
/*!********************************************************************************!*\
  !*** ./node_modules/css-loader/dist/cjs.js!./assets/react/disclosure-page.css ***!
  \********************************************************************************/
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
___CSS_LOADER_EXPORT___.push([module.i, "/*Disclosure Table Viewer CSS*/\n\n.fa-exclamation-triangle {\n  font-size: 100px;\n}\n\n.search-panel-td {\n  border-bottom: 0.5px #cecece solid;\n}\n\n.search-panel-table {\n  width: 100%\n}\n\n\n/*Disclosure List Homepage CSS*/\n\n.tr-results {\n  border-bottom: 1px solid black;\n  padding: 10px;\n  background: white;\n}\n", "",{"version":3,"sources":["webpack://./assets/react/disclosure-page.css"],"names":[],"mappings":"AAAA,8BAA8B;;AAE9B;EACE,gBAAgB;AAClB;;AAEA;EACE,kCAAkC;AACpC;;AAEA;EACE;AACF;;;AAGA,+BAA+B;;AAE/B;EACE,8BAA8B;EAC9B,aAAa;EACb,iBAAiB;AACnB","sourcesContent":["/*Disclosure Table Viewer CSS*/\n\n.fa-exclamation-triangle {\n  font-size: 100px;\n}\n\n.search-panel-td {\n  border-bottom: 0.5px #cecece solid;\n}\n\n.search-panel-table {\n  width: 100%\n}\n\n\n/*Disclosure List Homepage CSS*/\n\n.tr-results {\n  border-bottom: 1px solid black;\n  padding: 10px;\n  background: white;\n}\n"],"sourceRoot":""}]);
// Exports
/* harmony default export */ __webpack_exports__["default"] = (___CSS_LOADER_EXPORT___);


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
___CSS_LOADER_EXPORT___.push([module.i, "\n/*Stylize markdown viewer*/\n#markdown_viewer {\n  border: 1px solid;\n  border-color: lightgrey;\n  padding: 10px;\n  min-height: 100px;\n  border-top: none;\n}\n\n#react-root[data-page-owner='False'] > div > div#markdown_viewer {\n  border-top: 1px solid lightgrey;\n}\n\n/*Update the tables inside markdown viewer to look better*/\n#markdown_viewer table, #markdown_viewer thead, #markdown_viewer tbody, #markdown_viewer tr, #markdown_viewer td, #markdown_viewer th {\n  border: 1px solid;\n  padding:5px;\n}\n\n/*Provide consistent spacing on markdown viewing*/\n.view-only {\n  margin-top: 50px;\n  border: none;\n}\n\n/*Add consistent spacing for tabs*/\n#tab-tabs {\n    margin-top: 40px;\n}\n\n/*Make save button on markdown page more subtle*/\n#save_button {\n  margin-top: 2px;\n  border-radius: 2px;\n}\n\n/*Remove blue borders around tabs*/\nli:focus {\n  outline: 0;\n}\n\na:focus {\n  outline: 0;\n}\n\n/*Align content in tag tables and dropdown better*/\ntd  {\n  vertical-align: middle;\n}\n\n/*Stylize dropdown*/\n.delete-tag {\n  font-size: 10px;\n  line-height: 1.0;\n}\n\n/*Define toggle css in dropdown*/\nlabel.toggle input span {\n  border-radius: 2px;\n}\n\nlabel.toggle {\n  vertical-align: text-top;\n  height: 16px;\n  width: 28px;\n}\n\n/*Fix tag wrapping*/\nspan.tag {\n  white-space: nowrap;\n}\n\n/*Update color link on tag page back to tag list*/\n.tag-back {\n  color: #009;\n}\n\n/*Fixes mobile bug for button*/\n#tag-settings {\n  z-index: 1;\n}\n", "",{"version":3,"sources":["webpack://./assets/react/tag-page.css"],"names":[],"mappings":";AACA,0BAA0B;AAC1B;EACE,iBAAiB;EACjB,uBAAuB;EACvB,aAAa;EACb,iBAAiB;EACjB,gBAAgB;AAClB;;AAEA;EACE,+BAA+B;AACjC;;AAEA,0DAA0D;AAC1D;EACE,iBAAiB;EACjB,WAAW;AACb;;AAEA,iDAAiD;AACjD;EACE,gBAAgB;EAChB,YAAY;AACd;;AAEA,kCAAkC;AAClC;IACI,gBAAgB;AACpB;;AAEA,gDAAgD;AAChD;EACE,eAAe;EACf,kBAAkB;AACpB;;AAEA,kCAAkC;AAClC;EACE,UAAU;AACZ;;AAEA;EACE,UAAU;AACZ;;AAEA,kDAAkD;AAClD;EACE,sBAAsB;AACxB;;AAEA,mBAAmB;AACnB;EACE,eAAe;EACf,gBAAgB;AAClB;;AAEA,gCAAgC;AAChC;EACE,kBAAkB;AACpB;;AAEA;EACE,wBAAwB;EACxB,YAAY;EACZ,WAAW;AACb;;AAEA,mBAAmB;AACnB;EACE,mBAAmB;AACrB;;AAEA,iDAAiD;AACjD;EACE,WAAW;AACb;;AAEA,8BAA8B;AAC9B;EACE,UAAU;AACZ","sourcesContent":["\n/*Stylize markdown viewer*/\n#markdown_viewer {\n  border: 1px solid;\n  border-color: lightgrey;\n  padding: 10px;\n  min-height: 100px;\n  border-top: none;\n}\n\n#react-root[data-page-owner='False'] > div > div#markdown_viewer {\n  border-top: 1px solid lightgrey;\n}\n\n/*Update the tables inside markdown viewer to look better*/\n#markdown_viewer table, #markdown_viewer thead, #markdown_viewer tbody, #markdown_viewer tr, #markdown_viewer td, #markdown_viewer th {\n  border: 1px solid;\n  padding:5px;\n}\n\n/*Provide consistent spacing on markdown viewing*/\n.view-only {\n  margin-top: 50px;\n  border: none;\n}\n\n/*Add consistent spacing for tabs*/\n#tab-tabs {\n    margin-top: 40px;\n}\n\n/*Make save button on markdown page more subtle*/\n#save_button {\n  margin-top: 2px;\n  border-radius: 2px;\n}\n\n/*Remove blue borders around tabs*/\nli:focus {\n  outline: 0;\n}\n\na:focus {\n  outline: 0;\n}\n\n/*Align content in tag tables and dropdown better*/\ntd  {\n  vertical-align: middle;\n}\n\n/*Stylize dropdown*/\n.delete-tag {\n  font-size: 10px;\n  line-height: 1.0;\n}\n\n/*Define toggle css in dropdown*/\nlabel.toggle input span {\n  border-radius: 2px;\n}\n\nlabel.toggle {\n  vertical-align: text-top;\n  height: 16px;\n  width: 28px;\n}\n\n/*Fix tag wrapping*/\nspan.tag {\n  white-space: nowrap;\n}\n\n/*Update color link on tag page back to tag list*/\n.tag-back {\n  color: #009;\n}\n\n/*Fixes mobile bug for button*/\n#tag-settings {\n  z-index: 1;\n}\n"],"sourceRoot":""}]);
// Exports
/* harmony default export */ __webpack_exports__["default"] = (___CSS_LOADER_EXPORT___);


/***/ }),

/***/ "./node_modules/webpack/hot sync ^\\.\\/log$":
/*!*************************************************!*\
  !*** (webpack)/hot sync nonrecursive ^\.\/log$ ***!
  \*************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

var map = {
	"./log": "./node_modules/webpack/hot/log.js"
};


function webpackContext(req) {
	var id = webpackContextResolve(req);
	return __webpack_require__(id);
}
function webpackContextResolve(req) {
	if(!__webpack_require__.o(map, req)) {
		var e = new Error("Cannot find module '" + req + "'");
		e.code = 'MODULE_NOT_FOUND';
		throw e;
	}
	return map[req];
}
webpackContext.keys = function webpackContextKeys() {
	return Object.keys(map);
};
webpackContext.resolve = webpackContextResolve;
module.exports = webpackContext;
webpackContext.id = "./node_modules/webpack/hot sync ^\\.\\/log$";

/***/ }),

/***/ 1:
/*!****************************************************************************************************************!*\
  !*** multi (webpack)-dev-server/client?http://localhost:3000 (webpack)/hot/dev-server.js ./assets/react/index ***!
  \****************************************************************************************************************/
/*! no static exports found */
/***/ (function(module, exports, __webpack_require__) {

__webpack_require__(/*! /Users/palin/Code/courtlistener/cl/node_modules/webpack-dev-server/client/index.js?http://localhost:3000 */"./node_modules/webpack-dev-server/client/index.js?http://localhost:3000");
__webpack_require__(/*! /Users/palin/Code/courtlistener/cl/node_modules/webpack/hot/dev-server.js */"./node_modules/webpack/hot/dev-server.js");
module.exports = __webpack_require__(/*! ./assets/react/index */"./assets/react/index.tsx");


/***/ })

/******/ });
//# sourceMappingURL=main.js.map