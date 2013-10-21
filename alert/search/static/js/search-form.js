$(document).ready(function() {
    var cited_gt = $('#id_cited_gt');
    var cited_lt = $('#id_cited_lt');

    $('#extra-sidebar-fields').prependTo('#sidebar-facet-placeholder');
    $('#extra-sidebar-fields').show();

    $('#search-form, #sidebar-search-form').submit(function (e) {
        // Overrides the submit buttons so that they gather the correct
        // form elements before submission.
        e.preventDefault();

        // Empty the sliders if they are both at their max
        if (cited_gt.val() == 0 && cited_lt.val() == 15000){
            cited_gt.val("");
            cited_lt.val("");
        }

        // Gather all form fields that are necessary
        var gathered = $();
        if ($('#id_court_all:checked').length == 0) {
            // Add the court checkboxes that are selected
            gathered = gathered.add($('.court-checkbox:checked'));
        }
        if ($('.status-checkbox:checked').length <= $('.status-checkbox').length) {
            // Add the status checkboxes that are selected
            gathered = gathered.add($('.status-checkbox:checked'));
        }
        // Add the input boxes that aren't empty
        gathered = gathered.add($('.external-input:not([type=checkbox])').filter(function () {
            return this.value != "";
        }));
        gathered.each(function () {
            // Make and submit a hidden input element for all gathered fields
            var el = $(this);
            $('<input type="hidden" name="' + el.attr('name') + '" />')
                .val(el.val())
                .appendTo('#search-form');
        });
        document.location = '/?' + $('#search-form').serialize();
    });

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

    $('#id_court_all').click(function() {
        // Makes the check all box (un)check the other boxes
        $("input.court-checkbox:not(:disabled)").attr('checked', $('#id_court_all').is(':checked'));
    });
    $("input.court-checkbox").click(function(){
        if ($('input.court-checkbox:not(:disabled)').not(':checked').length == 0) {
            // If all checkboxes will be checked once this is checked, check the check all box.
            $("#id_court_all").attr('checked', true);
        } else {
            // Else, uncheck the check all.
            $("#id_court_all").attr('checked', false);
        }
    });

    $('.sidebar-section h3').click(function() {
        // Toggles the sidebar sections
        $(this).siblings('.hidden').toggle('fast');
        $(this).siblings('.shown').toggle('fast');
        $(this).toggleClass('arrow-right-before');
        $(this).toggleClass('arrow-down-before');
    });

    $('#create-alert-header').click(function(){
        // Puts the cursor in the alertName box when the create alert section is expanded.
        $('#id_alertName').focus();
    });
});
Modernizr.load({
    // Sets up HTML5 input placeholders in browsers that don't support them.
    test: Modernizr.placeholder,
    nope: '/static/js/placeholder-1.8.6.min.js',
    complete: function () { $('input, textarea').placeholder(); }
});
