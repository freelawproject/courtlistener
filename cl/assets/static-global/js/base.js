/*eslint-env browser */
/*global $, hopscotch */

$(document).ready(function() {
    // 'use strict'; // uncomment later on after full cleanup
    var citedGreaterThan = $('#id_cited_gt');
    var citedLessThan = $('#id_cited_lt');

    function makeSearchPath(tabSwitch) {
        // Empty the sliders if they are both at their max
        if (citedGreaterThan.val() === 0 && citedLessThan.val() === 20000) {
        // see https://github.com/freelawproject/courtlistener/issues/303
            citedGreaterThan.val('');
            citedLessThan.val('');
        }

        // Gather all form fields that are necessary
        var gathered = $();

        // If the user is switching tabs, then make sure their ordering is
        // valid for the tab they're headed to.
        var dropDown = $('#id_order_by');
        if (tabSwitch){
            var value;
            switch (dropDown.val()) {
                case 'dateFiled desc':
                    value = 'dateArgued desc';
                    break;
                case 'dateFiled asc':
                    value = 'dateArgued asc';
                    break;
                case 'dateArgued desc':
                    value = 'dateFiled desc';
                    break;
                case 'dateArgued asc':
                    value = 'dateFiled asc';
                    break;
                default:
                    value = 'score desc';
                    break;
            }
            var el = $('<input type="hidden" name="order_by" />').val(value);
            gathered = gathered.add(el);
        } else {
            // Not a tab switch; make sure to gather the element regardless.
            gathered = gathered.add(dropDown);
        }

        // Add the input boxes that aren't empty
        var selector = '.external-input[type=text]';
        gathered = gathered.add($(selector).filter(function () {
            return this.value !== '';
        }));

        // Add selected radio buttons
        gathered = gathered.add($('.external-input[type=radio]:checked'));

        // Add the court checkboxes that are selected as a single input element
        var checkedCourts = $('.court-checkbox:checked');
        if (checkedCourts.length !== $('.court-checkbox').length) {
            // Only do this if all courts aren't checked to keep URLs short.
            var values = [];
            for (var i = 0; i < checkedCourts.length; i++) {
                values.push(checkedCourts[i].id.split('_')[1]);
            }
            var courtString = values.join(' ');
            var el = jQuery('<input/>', {
                value: courtString,
                name: 'court'
            });
        }
        gathered = gathered.add(el);

        if ($('.status-checkbox:checked').length <= $('.status-checkbox').length) {
            // Add the status checkboxes that are selected
            gathered = gathered.add($('.status-checkbox:checked'));
        }

        // Add the hidden input used to indicate that we're editing an existing
        // alert
        gathered = gathered.add($('input[name=edit_alert]'));

        // Remove any inputs that are direct children of the form. These are
        // pernicious leftovers caused by the evils of the back button.
        $('#search-form > input').remove();

        gathered.each(function () {
            // Make and submit a hidden input element for all gathered fields
            var el = $(this);
            $('<input type="hidden" name="' + el.attr('name') + '" />')
                .val(el.val())
                .appendTo('#search-form');
        });
        var path = '/?' + $('#search-form').serialize();
        return path;
    }

    //////////////
    // Homepage //
    //////////////
    function showAdvancedHomepage() {
        $('#homepage #advanced-search-starter').hide();
        $('#homepage #advanced-search-inputs').show('fast').removeClass('hidden');
        $('#main-query-box').addClass('wide');
        $('#id_q').focus();
    }
    $('#homepage #advanced-search-starter a').click(function (event) {
        event.preventDefault();
        showAdvancedHomepage();
    });
    $('#show-all-statuses').click(function (event) {
        event.preventDefault();
        $('.status-item').removeClass('hidden');
        $('#show-all-statuses').addClass('hidden');
    });

    ///////////////////////
    // Search submission //
    ///////////////////////
    $('#search-form, ' +
      '#sidebar-search-form, ' +
      '.search-page #court-picker-search-form').submit(function (e) {
        e.preventDefault();

        // Ensure that the correct value is set in the radio button (correct
        // is defined by the label that is .selected). This is needed because
        // the "wrong" value will be selected after a user presses the back
        // button in their browser.
        $('#type-switcher .selected input').prop('checked', true);

        document.location = makeSearchPath(false);
    });

    $('#id_order_by').change(function () {
        $('#search-form').submit();
    });

    $('#homepage #court-picker-search-form').submit(function(e){
        e.preventDefault();

        // Indicate the count of selected jurisdictions when switching to
        // advanced search page.
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
            });
        }, 1500);
    });


    ///////////////////////////
    // Result Type Switching //
    ///////////////////////////
    $('#type-switcher label:not(.selected) input[name=type]').click(function () {
        // Note that we can't do submit here, because that'd trigger a
        // switching of the the checked radio button, and nothing would happen.
        document.location = makeSearchPath(true);
    });


    //////////////////
    // Court Picker //
    //////////////////
    function courtFilter () {
        var tabs = $('.tab-content'),
            checkboxes = tabs.find('.checkbox'),
            regex = new RegExp('\\b' + this.value, 'i'),
            matches = checkboxes.filter(function () {
                return regex.test($(this).find('label').text());
            });
        checkboxes.not(matches).find('input').prop('checked', false);
        matches.find('input').prop('checked', true);
    }

    $('#court-filter').keyup(courtFilter).change(courtFilter);

    // Check/clear the tab/everything
    $('#check-all').click(function() {
        $('#modal-court-picker .tab-pane input').prop('checked', true);
    });
    $('#clear-all').click(function () {
        $('#modal-court-picker .tab-pane input').prop('checked', false);
    });
    $('#check-current').click(function () {
        $('#modal-court-picker .tab-pane.active input').prop('checked', true);
    });
    $('#clear-current').click(function () {
        $('#modal-court-picker .tab-pane.active input').prop('checked', false);
    });


    ///////////////
    // RT Alerts //
    ///////////////
    $('#id_rate').change(function(){
        if ($(this).val() === 'rt' && totalDonatedLastYear < priceRtAlerts){
            $('#donate-for-rt').removeClass('hidden');
            $('#alertSave').prop("disabled", true);
        } else {
            // Reset the button, if needed.
            $('#donate-for-rt').addClass('hidden');
            $('#alertSave').prop("disabled", false);
        }
    });


    ////////////////
    // Auto Focus //
    ////////////////
    $('.auto-focus:first').focus();


    //////////
    // Tour //
    //////////
    var tour = {
        id: 'feature-tour',
        showPrevButton: true,
        steps: [
            {//0
                target: '#search-container',
                placement: 'bottom',
                xOffset: 'center',
                arrowOffset: 'center',
                title: 'Welcome to the Tour!',
                content: 'Broad queries can be a great way to start a ' +
                    'research task. Our search box can understand ' +
                    'everything you might expect&hellip; terms, concepts, ' +
                    'citations, you name it.',
                // If the advanced page is already shown, we skip to step 2.
                onNext: function(){
                    if (!$('#advanced-search-starter').is(':visible')){
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
                title: 'More Power Please!',
                content: 'If you are the kind of person that wants more ' +
                    'power, you\'ll love the advanced search box. ' +
                    'Click on \"Advanced Search\" to turn it on.',
                onNext: function(){
                    showAdvancedHomepage();
                }
            },
            {//2
                target: '#extra-sidebar-fields',
                placement: 'top',
                arrowOffset: 'center',
                zindex: 10,
                title: 'Sophisticated Search',
                content: 'In the Advanced Search area, you can make ' +
                    'sophisticated searches against a variety of fields. ' +
                    'Press \"Next\" and we\'ll make a query for you.',
                multipage: true,
                showPrevButton: false,
                onNext: function(){
                    window.location = '/?q=roe+v.+wade&order_by=score+desc&stat_Precedential=on&court=scotus';
                },
                delay: 250 // let advanced search area get exposed.
            },
            {//3
                // This step will be skipped if on a dev machine with no
                // results. Be not alarmed!
                target: document.querySelector('.search-page article'),
                placement: 'top',
                arrowOffset: 'center',
                title: 'Detailed Results',
                content: 'Here you can see the results for the query "Roe ' +
                    'v. Wade" sorted by relevance and filtered to only one ' +
                    'jurisdiction, the Supreme Court.',
                showPrevButton: false
            },
            {//4
                target: '#type-switcher',
                placement: 'bottom',
                arrowOffset: 'top',
                title: 'What are you Looking For?',
                content: 'By default you\'ll get opinion results, but use ' +
                    'this to research and listen to oral arguments instead.',
                showPrevButton: false
            },
            {//5
                target: '#create-alert-header',
                placement: 'top',
                arrowOffset: 'center',
                title: 'Make Alerts',
                content: '<p>Once you have placed a query, you can create ' +
                    'an alert. If there are ever any new results for your ' +
                    'query, CourtListener will send you an email to keep ' +
                    'you up to date.</p> <p>Hit next to check out <em>Roe ' +
                    'v. Wade</em>.</p>',
                multipage: true,
                onNext: function(){
                    window.location = '/opinion/108713/roe-v-wade/';
                }
            },
            {//6
                target: '#cited-by',
                placement: 'bottom',
                arrowOffset: 'center',
                title: 'The Power of Citation',
                content: 'Roe v. Wade has been cited hundreds of times since ' +
                    'it was issued in 1973. Looking at these citations can ' +
                    'be a good way to see related cases.'
            },
            {//7
                target: '#authorities',
                placement: 'top',
                arrowOffset: 'center',
                title: 'Authorities',
                showPrevButton: false,
                content: '<p>The Authorities section lists all of the ' +
                    'opinions that Roe v. Wade references. These can be ' +
                    'thought of as the principles it rests on.</p>' +
                    '<p>That\'s everything for now! Let us know if ' +
                    'you have any questions.</p>',
                onNext: function(){
                    hopscotch.endTour();
                }
            }
        ]
    };

    $('.tour-link').click(function (event) {
        event.preventDefault();
        var loc = location.pathname + location.search;
        if (loc !== '/') {
            sessionStorage.setItem('hopscotch.tour.state', 'feature-tour:0');
            window.location = '/';
        } else {
            hopscotch.startTour(tour, 0);
        }
    });
    // Start it automatically for certain steps.
    if (hopscotch.getState() === 'feature-tour:0') {
        hopscotch.startTour(tour);
    }
    if (hopscotch.getState() === 'feature-tour:3') {
        hopscotch.startTour(tour);
    }
    if (hopscotch.getState() === 'feature-tour:6') {
        hopscotch.startTour(tour);
    }

    ///////////////////////
    // Utility Functions //
    ///////////////////////
    // Make sure that a CSRF Header is sent with every ajax request.
    // https://docs.djangoproject.com/en/dev/ref/csrf/#ajax
    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie != '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = jQuery.trim(cookies[i]);
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) == (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    var csrfToken = getCookie('csrftoken');

    function csrfSafeMethod(method) {
        // these HTTP methods do not require CSRF protection
        return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
    }

    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrfToken);
            }
        }
    });
});


// Debounce - rate limit a function
// https://davidwalsh.name/javascript-debounce-function
function debounce(func, wait, immediate) {
    // Returns a function, that, as long as it continues to be invoked, will not
    // be triggered. The function will be called after it stops being called for
    // N milliseconds. If `immediate` is passed, trigger the function on the
    // leading edge, instead of the trailing.
    var timeout;
    return function () {
        var context = this, args = arguments;
        var later = function () {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        var callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
};
