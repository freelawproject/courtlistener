$(document).ready(function() {
    $('#extra-sidebar-fields').prependTo('#sidebar-facet-placeholder');
    $('#extra-sidebar-fields').show();
    
    $('#search-form,#sidebar-search-form').submit(function(e){
        // Overrides the submit buttons so that they gather the correct
        // form elements before submission.
        e.preventDefault();
        var refine = $('input[name=refine]:checked').val();
        if (refine == 'new') {
            // If it's a new query, we only persist the sort order.
            gathered = $('#id_sort');
        }
        else {
            // Otherwise, all form fields are persisted that are necessary
        	var gathered = $();
        	if ($('#id_court_all:checked').length == 0) {
        		// All courts are not selected, therefore add the court checkboxes  
        		gathered = gathered.add($('.court-checkbox:checked'));
        	} 
        	if ($('.status-checkbox:checked').length < $('.status-checkbox').length){
            	// All statuses are not checked, therefore add the status checkboxes
        		gathered = gathered.add($('.status-checkbox:checked'));
        	}
        	// Add the input boxes that aren't empty
        	gathered = gathered.add($('.external-input:not([type=checkbox])').filter(function() { return this.value != ""; }));
    	}
        gathered.each(function() {
           var el = $(this);
           $('<input type="hidden" name="' + el.attr('name') + '" />')
               .val(el.val())
               .appendTo('#search-form');
        });
        document.location = '/?' + $('#search-form').serialize();
    });
    
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
    nope: '/media/js/placeholder-1.8.6.min.js',
    complete: function () { $('input, textarea').placeholder(); }
});