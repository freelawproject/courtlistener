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


    ///////////////////////////
    // New Viz Functionality //
    ///////////////////////////
    var dateFiledQ = '((dateFiled:[1945-01-01T00:00:00Z TO ' + last_year + 'Z] AND scdb_id:["" TO *]) OR (dateFiled:[' + last_year + 'Z TO *]))';
    var authorityIDs = {};
    var updateAuthorityCache = function (suggestion, callback) {
        // Check if we have the ID in our cache. If so, do nothing. If not,
        // load up the cache.
        if (suggestion.id in authorityIDs) {
            // All good; do nothing; pass
        } else {
            // Get the IDs, add them as a new key.
            // Get a list of the IDs cited by the item and cache it. This cache
            // is needed to do the reverse lookup for authorities.
            $.ajax({
                'method': 'GET',
                'url': "/api/rest/v3/search/",
                'data': {
                    q: "id:" + suggestion.id,
                    format: 'json'
                }
            }).done(function (data) {
                authorityIDs[suggestion.id]['ids'] = data.results[0].cites || [];
                if (authorityIDs[suggestion.id]['ids'].length > 0) {
                    $.ajax({
                        // We have the authority IDs, but we don't know how many
                        // are SCOTUS cases in the right date range.
                        'method': 'GET',
                        'url': "/api/rest/v3/search/",
                        'data': {
                            q: dateFiledQ + " AND id:(" + authorityIDs[suggestion.id].ids.join(" OR ") + ")",
                            court: 'scotus',
                            format: 'json'
                        }
                    }).done(function (data) {
                        authorityIDs[suggestion.id]['count'] = data.results.length;
                        callback(suggestion);
                    });
                } else {
                    authorityIDs[suggestion.id]['count'] = 0;
                    callback(suggestion);
                }
            });
        }
    };

    var identify = function (obj) {
        // Return the item ID so the system can have a unique id for it
        // in its caches.
        return obj.id;
    };
    var transform = function (response) {
        // Pull the results dict out of the main object.
        return response.results
    };
    var remotePrepare = function (query, settings) {
        // This query is anything with the case name typed in...
        // ...in the supreme court...
        // ...between 1945 and a year ago that has an SCDB id... OR
        // ...in the last year, with or without an SCDB id.
        var params = {
            court: 'scotus',
            q: dateFiledQ,
            format: 'json'
        };
        if (query.length > 0) {
            // Add a case name parameter, if the user has typed something.
            params.case_name = "(%QUERY) OR (%QUERY*)".replace(
                /%QUERY/g, $.trim(query));
        }

        var start_id = $('#id_cluster_start').val();
        if ($("#ending-cluster-typeahead-search").is(":focus")) {
            // Pass. No extra params required to do simple search.
        } else if ($("#ending-cluster-typeahead-authorities").is(":focus")) {
            // Append the authority IDs onto the end of the query.
            params.q += " AND id:(" + authorityIDs[start_id].ids.join(" OR ") + ")";
        } else if ($("#ending-cluster-typeahead-citing").is(":focus")) {
            // Append the cited_by ID onto the end of the query.
            params.q += " AND cites:(" + start_id + ")";
        }

        return settings.url + $.param(params);
    };

    var searchResultsStartingCluster = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace('caseName'),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        sufficient: 21,
        matchAnyQueryToken: true,
        identify: identify,
        remote: {
            url: '/api/rest/v3/search/?',
            prepare: remotePrepare,
            transform: transform
        }
    });
    var searchResultsEndingClusterSearch = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace('caseName'),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        sufficient: 21,
        matchAnyQueryToken: true,
        identify: identify,
        remote: {
            url: '/api/rest/v3/search/?',
            prepare: remotePrepare,
            transform: transform
        }
    });
    var searchResultsEndingClusterAuthorities = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace('caseName'),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        sufficient: 21,
        matchAnyQueryToken: true,
        identify: identify,
        remote: {
            url: '/api/rest/v3/search/?',
            prepare: remotePrepare,
            transform: transform
        }
    });
    var searchResultsEndingClusterCiting = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace('caseName'),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        sufficient: 21,
        matchAnyQueryToken: true,
        identify: identify,
        remote: {
            url: '/api/rest/v3/search/?',
            prepare: remotePrepare,
            transform: transform
        }
    });

    var showFields = function (obj) {
        // Make a nice concatenation of citations, case name and year.
        var parts = [obj.caseName];
        if (obj.dateFiled) {
            parts.push(new Date(obj.dateFiled).getUTCFullYear());
        }
        if (obj.citation) {
            parts.push(obj.citation.join(", "));
        }
        return parts.join(" – ");
    };

    $('#starting-cluster-typeahead').typeahead({
            'hint': false,
            'highlight': true,
            'minLength': 0
        },
        {
            display: showFields,
            limit: 19,  // Must be less than the 'sufficient' param in searchResults.
            source: searchResultsStartingCluster
        }
    );
    $('#ending-cluster-typeahead-search').typeahead({
            'hint': false,
            'highlight': true,
            'minLength': 0
        },
        {
            display: showFields,
            limit: 19,  // Must be less than the 'sufficient' param in searchResults.
            source: searchResultsEndingClusterSearch
        }
    );
    $('#ending-cluster-typeahead-authorities').typeahead({
            'hint': false,
            'highlight': true,
            'minLength': 0
        },
        {
            display: showFields,
            limit: 19,  // Must be less than the 'sufficient' param in searchResults.
            source: searchResultsEndingClusterAuthorities
        }
    );
    $('#ending-cluster-typeahead-citing').typeahead({
            'hint': false,
            'highlight': true,
            'minLength': 0
        },
        {
            display: showFields,
            limit: 19,  // Must be less than the 'sufficient' param in searchResults.
            source: searchResultsEndingClusterCiting
        }
    );


    $('#starting-cluster-typeahead').bind(
        'typeahead:select',
        function (ev, suggestion) {
            updateAuthorityCache(suggestion, function(suggestion) {
                $('.authority-count').text("(" + authorityIDs[suggestion.id].count + ")");
                $('input[disabled="disabled"]').prop('disabled', false);
            });
            $('#id_cluster_start').val(suggestion.id);
            $('.first-selection').text(suggestion.caseNameShort || suggestion.caseName);
        });
    $('.ending-typeahead').bind(
        'typeahead:select',
        function (ev, suggestion) {
            $('#id_cluster_end').val(suggestion.id);
        });
    $('a[data-toggle="tab"]').on('show.bs.tab', function (e) {
        $('.ending-typeahead').val("");
    });

    // Extra options JS
    $('#more').click(function(e){
        $('#center-buttons').addClass('hidden');
        $('#extra-options').removeClass('hidden');
    });
});
