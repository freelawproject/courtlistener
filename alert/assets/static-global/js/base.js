$(document).ready(function() {
    var cited_gt = $('#id_cited_gt');
    var cited_lt = $('#id_cited_lt');

    function makeSearchPath(){
        // Empty the sliders if they are both at their max
        if (cited_gt.val() == 0 && cited_lt.val() == 15000) {
            cited_gt.val("");
            cited_lt.val("");
        }

        // Gather all form fields that are necessary
        var gathered = $();

        // Add the input boxes that aren't empty
        gathered = gathered.add($('.external-input:not([type=checkbox])').filter(function () {
            return this.value != "";
        }));

        // Add the court checkboxes that are selected as a single input element
        var checked_courts = $('.court-checkbox:checked');
        if (checked_courts.length != $('.court-checkbox').length) {
            // Only do this if all courts aren't checked to keep URLs short.
            var values = [];
            for (var i = 0; i < checked_courts.length; i++) {
                values.push(checked_courts[i].id.split('_')[1]);
            }
            var court_str = values.join(" ");
            var el = jQuery('<input/>', {
                value: court_str,
                name: 'court'
            });
        }

        gathered = gathered.add(el);

        if ($('.status-checkbox:checked').length <= $('.status-checkbox').length) {
            // Add the status checkboxes that are selected
            gathered = gathered.add($('.status-checkbox:checked'));
        }

        gathered.each(function () {
            // Make and submit a hidden input element for all gathered fields
            var el = $(this);
            $('<input type="hidden" name="' + el.attr('name') + '" />')
                .val(el.val())
                .appendTo('#search-form');
        });
        var path = '/?' + $('#search-form').serialize();
        return path
    }

    //////////////
    // Homepage //
    //////////////
    function showAdvancedHomepage() {
        $('#homepage #advanced-search-starter, #homepage #search-container td > i').hide();
        $('#homepage #advanced-search-inputs').show("fast");
        $("#main-query-box").addClass('wide');
        $('#id_q').focus();
    }
    $('#homepage #advanced-search-starter h3').click(function () {
        showAdvancedHomepage();
    });

    ///////////////////////
    // Search submission //
    ///////////////////////
    $('#search-form, #sidebar-search-form, .search-page #court-picker-search-form').submit(function (e) {
        // Overrides the submit buttons so that they gather the correct
        // form elements before submission.
        e.preventDefault();
        document.location = makeSearchPath();
    });

    $('#homepage #court-picker-search-form').submit(function(e){
        e.preventDefault();
        $('#jurisdiction-count').text($(this).find('input:checked').length);
        $('#court-picker').modal('hide');
        showAdvancedHomepage();
        $('#jurisdiction-count').css({
            'background-color': 'yellow',
            'font-weight': 'bold'
        });
        setTimeout(function () {
            $('#jurisdiction-count').css({
                'background-color': 'transparent',
                'font-weight': 'normal'
            })
        }, 1000);
    });


    ////////////
    // Slider //
    ////////////
    if (cited_gt.val() == "") {
        cited_gt.val(0);
    }
    if (cited_lt.val() == ""){
        cited_lt.val(15000);
    }
    $(function() {
        // Load up the slider in the UI
        $("#slider-range").slider({
            range: true,
            min: 0,
            max: 15000,
            step: 10,
            values: [cited_gt.val(),
                     cited_lt.val()],
            slide: function(event, ui) {
                // Update the text
                if (ui.values[0] == 0 && ui.values[1] == 15000){
                    $('#citation-count').text("(Any)");
                } else {
                    $("#citation-count").text( "(" + ui.values[0] + " - " + ui.values[1] + ")");
                }
                cited_gt.val(ui.values[0]);
                cited_lt.val(ui.values[1]);
            }
        });
    });
    if (cited_gt.val() != 0 || cited_lt.val() != 15000) {
        $('#citation-count').text("(" + $("#id_cited_gt").val() + " - " + $("#id_cited_lt").val() + ")")
    }

    //////////////////
    // Court Picker //
    //////////////////
    function listFilter(list, input) {
        var checkbox_sections = list.find('.sidebar-checkbox');
        function filter() {
            var regex = new RegExp('\\b' + this.value, "i");
            var $els = checkbox_sections.filter(function () {
                return regex.test($(this).find('label').text());
            });
            checkbox_sections.not($els).find('input').prop('checked', false);
            $els.find('input').prop('checked', true);
        }
        input.keyup(filter).change(filter)
    }
    jQuery(function ($) {
        listFilter($('.tab-content'), $('#court-filter'));
    });

    // Check/clear the tab/everything
    $('#check-all').click(function() {
        $("#modal-court-picker .tab-pane input").prop('checked', true);
    });
    $('#clear-all').click(function () {
        $("#modal-court-picker .tab-pane input").prop('checked', false);
    });
    $('#check-current').click(function () {
        $("#modal-court-picker .tab-pane.active input").prop('checked', true);
    });
    $('#clear-current').click(function () {
        $("#modal-court-picker .tab-pane.active input").prop('checked', false);
    });

    //////////
    // Tour //
    //////////
    var tour = new Tour({
        steps: [
            {
                path: '/',
                element: '#id_q',
                placement: 'bottom',
                title: 'Welcome to the tour!',
                content: 'Broad queries can be a great way to start a research task. Our search box can understand ' +
                    'everything you might expect...terms, concepts, citations, you name it.'
            },
            {
                path: '/',
                element: '#advanced-search-starter',
                placement: 'bottom',
                reflex: true,
                title: 'More power please!',
                content: "If you are the kind of person that wants more power, you'll love the advanced search box. " +
                    "Click on \"Advanced Search\" to turn it on.",
                onNext: function(){
                    showAdvancedHomepage();
                }
            },
            {
                path: '/',
                element: "#extra-sidebar-fields",
                backdrop: true,
                title: "Sophisticated Search",
                content: "In the Advanced Search area, you can make sophisticated searches against many fields. " +
                    "Press \"Next\" and we'll make a query for you."
            },
            {
                /*onShow: function () {
                    window.location = '/?q=test&court=scotus&stat_Precedential=on&order_by=score+desc';
                },*/
                path: '/',
                element: '.search-page article:first',
                placement: 'top',
                orphan: true,
                title: 'Detailed Results',
                content: 'Here you can see the results for the query "Roe v Wade" sorted by relevance and filtered to ' +
                    'only one jurisdiction, the Supreme Court.'
            },
            {
                path: '/',
                element: '#create-alert-header',
                placement: 'right',
                title: 'Make alerts',
                content: 'Once you have placed a query, you can create an alert. If there are ever any new results for ' +
                    'your query, CourtListener will send you an email. Hit next to check out Roe v. Wade.'
            },
            {
                path: '/scotus/eq/town-of-greece-v-galloway/', //'/scotus/yjn/roe-v-wade/',
                element: '#cited-by',
                orphan: true,
                placement: 'right',
                title: 'The Power of Citation',
                content: 'Roe v. Wade has been cited hundreds of times since it was issued in 1973. Looking at these ' +
                    'citations can be a good way to see related cases.'
            },
            {
                path: '/scotus/eq/town-of-greece-v-galloway/', //'/scotus/yjn/roe-v-wade/',
                element: '#authorities',
                placement: 'right',
                title: 'Authorities',
                content: 'The Authorities section lists all of the opinions that Roe v. Wade references. These can be ' +
                    'thought of as the principles it rests on.'
            },
            {
                orphan: true,
                title: 'Thanks',
                content: 'This concludes a brief tour of some of our features. We hope you enjoy using CourtListener, ' +
                    'and if you have any questions do not hesitate to get in touch.'
            }
        ],
        debug: true
    });
    tour._isRedirect = function(path, currentPath){
        return (path != null) && //Return false if path is undefined.
            path !== "" && (
            ({}.toString.call(path) === "[object RegExp]" && !path.test(currentPath)) ||
                ({}.toString.call(path) === "[object String]" &&
                    path.replace(/\/?$/, "") !== currentPath.replace(/\/?$/, "")
                    )
            );
    }

    tour.init();
    $('#tour-link').click(function () {
        tour.restart();
        tour.start(true);
    });
});


Modernizr.load({
    // Sets up HTML5 input placeholders in browsers that don't support them.
    test: Modernizr.placeholder,
    nope: '/static/js/placeholder-1.8.6.min.js',
    complete: function () { $('input, textarea').placeholder(); }
});
