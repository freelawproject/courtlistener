$(document).ready(function () {
    var dateFiledQ = '((dateFiled:[* TO ' + last_year + 'Z] AND scdb_id:["" TO *]) OR (dateFiled:[' + last_year + 'Z TO *]))';
    var cache = {};
    var setAuthorityIDs = function (id, cb) {
        $.ajax({
            method: 'GET',
            url: "/api/rest/v3/search/",
            data: {
                q: "cluster_id:" + id,
                format: 'json'
            },
            success: function (data) {
                cache[id] = {'authority_ids': data.results[0].cites || []};
            }
        }).done(function () {
            cb(id);
        });
    };
    var setAuthorityCount = function (id, cb) {
        cache[id]['authority_count'] = 0;  // Set the default.
        if (cache[id]['authority_ids'].length > 0) {
            $.ajax({
                // We have the authority IDs, but we don't know how many
                // are SCOTUS cases in the right date range.
                'method': 'GET',
                'url': "/api/rest/v3/search/",
                'data': {
                    q: dateFiledQ +
                    " AND id:(" +
                    cache[id].authority_ids.join(" OR ") +
                    ")",
                    court: 'scotus',
                    format: 'json'
                },
                success: function (data) {
                    cache[id]['authority_count'] = data.count;
                }
            }).done(function () {
                cb();
            });
        } else {
            cb();
        }
    };
    var setCitingCount = function (id, cb) {
        cache[id]['citing_count'] = 0;  // Set the default
        $.ajax({
            method: 'GET',
            url: "/api/rest/v3/search/",
            data: {
                q: dateFiledQ + " AND cites:(" + id + ")",
                court: 'scotus',
                format: 'json'
            },
            success: function (data) {
                cache[id]['citing_count'] = data.count;
            }
        }).done(function () {
            cb();
        });
    };
    var updateCache = function (suggestion, callback) {
        // Check if we have the ID in our cache. If so, do nothing. If not,
        // load up the cache.
        if (suggestion.cluster_id in cache) {
            // All good; do nothing; pass
        } else {
            // Get the authority IDs as the
            setAuthorityIDs(suggestion.cluster_id, function () {
                setAuthorityCount(suggestion.cluster_id, function () {
                    setCitingCount(suggestion.cluster_id, function () {
                        callback(suggestion);
                    });
                });
            });
        }
    };

    var getParamsForQuery = function (query) {
        // This query is anything with the case name typed in...
        // ...in the supreme court...
        // ...that has an SCDB id... OR
        // ...in the last year, with or without an SCDB id.
        var params = {
            court: 'scotus',
            q: dateFiledQ,
            format: 'json'
        };
        if ($.trim(query).length > 0) {
            // Add a case name parameter, if the user has typed something.
            params.case_name = "(%QUERY) OR (%QUERY*)".replace(
                /%QUERY/g, $.trim(query));
        }

        var start_id = $('#id_cluster_start').val();
        if ($("#ending-cluster-typeahead-search").is(":focus")) {
            // Pass. No extra params required to do simple search.
        } else if ($("#ending-cluster-typeahead-authorities").is(":focus")) {
            // Append the authority IDs onto the end of the query.
            params.q += " AND id:(" + cache[start_id].authority_ids.join(" OR ") + ")";
            // Add a cache busting param to defeat bloodhound's cache.
        } else if ($("#ending-cluster-typeahead-citing").is(":focus")) {
            // Append the cited_by ID onto the end of the query.
            params.q += " AND cites:(" + start_id + ")";
        }

        return params;
    };

    var display = function (obj) {
        // Make a concatenation of citations, case name and year.
        var parts = [obj.caseName];
        if (obj.dateFiled) {
            parts.push(new Date(obj.dateFiled).getUTCFullYear());
        }
        if (obj.citation) {
            parts.push(obj.citation[0]);
        }
        return parts.join(" – ");
    };
    var source = function (q, sync, async) {
        var params = getParamsForQuery(q);
        return $.ajax({
            method: 'GET',
            url: "/api/rest/v3/search/",
            data: params,
            success: function (data) {
                return async(data.results);
            }
        });
    };
    var optionsNoMin = {
        'hint': false,
        'highlight': true,
        'minLength': 0
    };
    var optionsMinSet = {
        'hint': false,
        'highlight': true,
        'minLength': 3
    };
    var resultOptions = {
        display: display,
        limit: 20,
        source: debounce(source, 300)
    };

    $("#starting-cluster-typeahead, #ending-cluster-typeahead-search")
        .typeahead(optionsMinSet, resultOptions);
    $('#ending-cluster-typeahead-citing, #ending-cluster-typeahead-authorities')
        .typeahead(optionsNoMin, resultOptions);


    $('#starting-cluster-typeahead').on(
        'typeahead:select',
        function (ev, suggestion) {
            updateCache(suggestion, function (suggestion) {
                $('.authority-count')
                    .text("(" + cache[suggestion.cluster_id].authority_count + ")");
                $('.citing-count')
                    .text("(" + cache[suggestion.cluster_id].citing_count + ")");
                $('input[disabled="disabled"]').prop('disabled', false);
            });
            $('#id_cluster_start').val(suggestion.cluster_id);
            $('.first-selection')
                .text(suggestion.caseNameShort || suggestion.caseName);
        });
    $('.ending-typeahead').on(
        'typeahead:select',
        function (ev, suggestion) {
            $('#id_cluster_end').val(suggestion.cluster_id);
        });
    $('a[data-toggle="tab"]').on('show.bs.tab', function (e) {
        $('.ending-typeahead').typeahead('val', "");
    });

    // Extra options JS
    $('#more').on("click", function (e) {
        $('#more').addClass('hidden');
        $('#extra-options').removeClass('hidden');
    });
});
