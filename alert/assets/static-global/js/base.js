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
        var selector = '.external-input:not([type=checkbox]):not([type=radio])';
        gathered = gathered.add($(selector).filter(function () {
            return this.value != "";
        }));

        // Add selected radio buttons
        gathered = gathered.add($('.external-input[type=radio]:checked'));

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
    $('#search-form, #sidebar-search-form, ' +
        '.search-page #court-picker-search-form').submit(function (e) {
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

    ///////////////////
    // Tab Switching //
    ///////////////////
    $('input[name=source]').change(function () {
        // Map or eliminate the ordering drop down's value, then submit.
        var drop_down = $('#id_order_by');
        if (drop_down.val() === 'dateFiled desc'){
            drop_down.val('dateArgued desc');
        } else if (drop_down.val() === 'dateFiled asc'){
            drop_down.val('dateArgued asc');
        } else if (drop_down.val() === 'dateArgued desc'){
            drop_down.val('dateFiled desc')
        } else if (drop_down.val() === 'dateArgued asc') {
            drop_down.val('dateFiled asc')
        } else if (drop_down.val() === 'score desc') {
            // Do nothing, but this block prevents the else clause from
            // triggering.
        } else {
                drop_down.val('')
        }
        $('#search-form').submit();
    });

    //////////
    // Tour //
    //////////
    var tour = {
        id: "feature-tour",
        showPrevButton: true,
        steps: [
            {//0
                target: '#id_q',
                placement: 'bottom',
                xOffset: 'center',
                arrowOffset: 'center',
                title: 'Welcome to the tour!',
                content: 'Broad queries can be a great way to start a research task. Our search box can understand ' +
                    'everything you might expect...terms, concepts, citations, you name it.',
                // If the advanced page is already shown, we skip to step 2.
                onNext: function(){
                    if (!$('#advanced-search-starter').is(":visible")){
                        hopscotch.showStep(2);
                    }
                }
            },
            {//1
                target: '#advanced-search-starter',
                placement: 'bottom',
                xOffset: 'center',
                arrowOffset: 'center',
                nextOnTargetClick: true,
                title: 'More power please!',
                content: "If you are the kind of person that wants more power, you'll love the advanced search box. " +
                    "Click on \"Advanced Search\" to turn it on.",
                onNext: function(){
                    showAdvancedHomepage();
                }
            },
            {//2
                target: "#extra-sidebar-fields",
                placement: 'right',
                arrowOffset: 'center',
                title: "Sophisticated Search",
                content: "In the Advanced Search area, you can make sophisticated searches against many fields. " +
                    "Press \"Next\" and we'll make a query for you.",
                multipage: true,
                onNext: function(){
                    window.location = '/?q=roe+v.+wade&order_by=score+desc&stat_Precedential=on&court=scotus';
                }
            },
            {//3
                target: document.querySelector('.search-page article'),
                placement: 'top',
                arrowOffset: 'center',
                title: 'Detailed Results',
                content: 'Here you can see the results for the query "Roe v. Wade" sorted by relevance and filtered to ' +
                    'only one jurisdiction, the Supreme Court.'
            },
            {//4
                target: '#create-alert-header',
                placement: 'right',
                arrowOffset: 'center',
                title: 'Make alerts',
                content: '<p>Once you have placed a query, you can create an alert. If there are ever any new results for ' +
                    'your query, CourtListener will send you an email.</p> <p>Hit next to check out Roe v. Wade.</p>',
                multipage: true,
                onNext: function(){
                    window.location = '/scotus/yjn/roe-v-wade/';
                }
            },
            {//5
                target: '#cited-by',
                placement: 'right',
                arrowOffset: 'center',
                title: 'The Power of Citation',
                content: 'Roe v. Wade has been cited hundreds of times since it was issued in 1973. Looking at these ' +
                    'citations can be a good way to see related cases.'
            },
            {//6
                target: '#authorities',
                placement: 'right',
                arrowOffset: 'center',
                title: 'Authorities',
                content: '<p>The Authorities section lists all of the opinions that Roe v. Wade references. These can be ' +
                    'thought of as the principles it rests on.</p><p>That\'s everything for now! Let us know if ' +
                    'you have any questions.</p>',
                onNext: function(){
                    hopscotch.endTour();
                }
            }
        ]
    };

    $('#tour-link').click(function () {
        var loc = location.pathname + location.search;
        if (loc !== '/') {
            sessionStorage.setItem("hopscotch.tour.state", 'feature-tour:0');
            window.location = '/';
        } else {
            hopscotch.startTour(tour, 0);
        }
    });
    // Start it automatically for certain steps.
    if (hopscotch.getState() === "feature-tour:0") {
        hopscotch.startTour(tour);
    }
    if (hopscotch.getState() === "feature-tour:3") {
        hopscotch.startTour(tour);
    }
    if (hopscotch.getState() === "feature-tour:5") {
        hopscotch.startTour(tour);
    }
});


Modernizr.load({
    // Sets up HTML5 input placeholders in browsers that don't support them.
    test: Modernizr.placeholder,
    nope: '/static/js/placeholder-1.8.6.min.js',
    complete: function () { $('input, textarea').placeholder(); }
});
