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

    /////////////////////
    // Form submission //
    /////////////////////
    $('#search-form, #sidebar-search-form, #court-picker-search-form').submit(function (e) {
        // Overrides the submit buttons so that they gather the correct
        // form elements before submission.
        e.preventDefault();
        document.location = makeSearchPath();
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
    $('.clear-filter').click(function () {
        // Clears the input box and reshows any filtered boxes.
        $('#court-filter').val('');
        $('.visible-count p').hide();
        $('.sidebar-checkbox').show();
    });
    $('#check-all').click(function() {
        // Makes the check all box (un)check the other boxes
        $("#modal-court-picker .tab-pane input").prop('checked', true);
    });
    $('#clear-all').click(function () {
        // Makes the check all box (un)check the other boxes
        $("#modal-court-picker .tab-pane input").prop('checked', false);
    });
    $('#check-current').click(function () {
        // Makes the check all box (un)check the other boxes
        $("#modal-court-picker .tab-pane.active input").prop('checked', true);
    });
    $('#clear-current').click(function () {
        // Makes the check all box (un)check the other boxes
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
                content: 'Broad queries can be a great way to start a research task. Type in a query and press next to get started.',
                redirect: function () {
                    document.location.href = makeSearchPath();
                }
            },
            {
                path: new RegExp('/*'),
                element: "#create-alert-header",
                title: "Create Alerts",
                content: "You can create alerts for many jurisdictions to get the latest updates."
            }
        ],
        debug: true,
        storage: false
    });
    tour.init();
    $('#tour-link').click(function () {
        tour.start(true);
    });
});


Modernizr.load({
    // Sets up HTML5 input placeholders in browsers that don't support them.
    test: Modernizr.placeholder,
    nope: '/static/js/placeholder-1.8.6.min.js',
    complete: function () { $('input, textarea').placeholder(); }
});
