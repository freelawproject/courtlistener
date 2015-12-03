$(document).ready(function () {
    ///////////////////////////////////
    // Trash & Restore Functionality //
    ///////////////////////////////////
    $(".trash-button, .restore-button").click(function (event) {
        event.preventDefault();
        var button = $(this),
            id = button.data('id'),
            buttonIcon = button.find('i'),
            parentRow = button.closest('tr'),
            pageType,
            message;

        buttonIcon.removeClass("fa-trash-o");
        buttonIcon.addClass("fa-spinner fa-pulse");
        if (window.location.href.indexOf("deleted") >= 0){
            // We're on the deleted page, trying to restore.
            pageType = "trash";
        } else {
            pageType = "active";
        }

        $.ajax({
            method: "POST",
            url: "/visualizations/scotus-mapper" + (pageType == 'trash' ? "/restore/" : "/delete/"),
            data: {pk: id},
            success: function () {
                $('.bootstrap-growl').alert("close");
                parentRow.fadeOut('slow');
                if (pageType == "trash") {
                    message = "Your item was restored successfully."
                } else {
                    message = "Your item was moved to the trash."
                }
                $.bootstrapGrowl(
                    message,
                    {
                        type: "success",
                        align: "center",
                        width: "auto",
                        delay: 2000,
                        allow_dismiss: false,
                        offset: {from: 'top', amount: 80}
                    }
                );
            },
            error: function () {
                buttonIcon.removeClass("fa-spinner fa-pulse");
                buttonIcon.addClass("fa-trash-o");
                if (pageType == "trash") {
                    message = "An error occurred. Unable to restore your item."
                } else {
                    message = "An error occurred. Unable to move your item to the trash."
                }
                $.bootstrapGrowl(
                    message,
                    {
                        type: "danger",
                        align: "center",
                        width: "auto",
                        delay: 2000,
                        allow_dismiss: false,
                        offset: {from: 'top', amount: 80}
                    }
                );
            }
        });
    });
    $(function () {
        // Initialize tooltips on this page.
        $('[data-toggle="tooltip"]').tooltip()
    });


    //////////////////////////////
    // Create Viz Functionality //
    //////////////////////////////
    var dateFiledQ = '((dateFiled:[1945-01-01T00:00:00Z TO ' + last_year + 'Z] AND scdb_id:["" TO *]) OR (dateFiled:[' + last_year + 'Z TO *]))';
    var cache = {};
    var setAuthorityIDs = function(id, cb){
        $.ajax({
            method: 'GET',
            url: "/api/rest/v3/search/",
            data: {
                q: "id:" + id,
                format: 'json'
            },
            success: function(data){
                cache[id] = {'authority_ids': data.results[0].cites || []};
            }
        }).done(function(){
            cb(id);
        });
    };
    var setAuthorityCount = function(id, cb) {
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
                success: function(data){
                    cache[id]['authority_count'] = data.count;
                }
            }).done(function(){
                cb();
            });
        } else {
            cb();
        }
    };
    var setCitingCount = function(id, cb){
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
        }).done(function(){
            cb();
        });
    };
    var updateCache = function (suggestion, callback) {
        // Check if we have the ID in our cache. If so, do nothing. If not,
        // load up the cache.
        if (suggestion.id in cache) {
            // All good; do nothing; pass
        } else {
            // Get the authority IDs as the
            setAuthorityIDs(suggestion.id, function(){
                setAuthorityCount(suggestion.id, function(){
                    setCitingCount(suggestion.id, function(){
                        callback(suggestion);
                    });
                });
            });
        }
    };

    var getParamsForQuery = function (query) {
        // This query is anything with the case name typed in...
        // ...in the supreme court...
        // ...between 1945 and a year ago that has an SCDB id... OR
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


    $('.typeahead').typeahead({
            'hint': false,
            'highlight': true,
            'minLength': 0
        },
        {
            display: function (obj) {
                // Make a nice concatenation of citations, case name and year.
                var parts = [obj.caseName];
                if (obj.dateFiled) {
                    parts.push(new Date(obj.dateFiled).getUTCFullYear());
                }
                if (obj.citation) {
                    parts.push(obj.citation.join(", "));
                }
                return parts.join(" – ");
            },
            limit: 20,
            source: debounce(function (q, sync, async) {
                var params = getParamsForQuery(q);
                return $.ajax({
                    method: 'GET',
                    url: "/api/rest/v3/search/",
                    data: params,
                    success: function (data) {
                        return async(data.results);
                    }
                });
            }, 300)
        }
    );


    $('#starting-cluster-typeahead').bind(
        'typeahead:select',
        function (ev, suggestion) {
            updateCache(suggestion, function(suggestion) {
                $('.authority-count')
                    .text("(" + cache[suggestion.id].authority_count + ")");
                $('.citing-count')
                    .text("(" + cache[suggestion.id].citing_count + ")");
                $('input[disabled="disabled"]').prop('disabled', false);
            });
            $('#id_cluster_start').val(suggestion.id);
            $('.first-selection')
                .text(suggestion.caseNameShort || suggestion.caseName);
        });
    $('.ending-typeahead').bind(
        'typeahead:select',
        function (ev, suggestion) {
            $('#id_cluster_end').val(suggestion.id);
        });
    $('a[data-toggle="tab"]').on('show.bs.tab', function (e) {
        $('.ending-typeahead').typeahead('val', "");
    });

    // Extra options JS
    $('#more').click(function(e){
        $('#center-buttons').addClass('hidden');
        $('#extra-options').removeClass('hidden');
    });
});
