$(document).ready(function() {
    $("#favorite-star-png, #edit-favorite").click(function () {
        $("#modal-save-favorite").toggle();
        $("#save-favorite-name-field").focus();
    });
    $("#favorite-star-png").click(function () {
        // This only works if the user is logged out
        $('#modal-logged-out').fadeToggle('slow');
    });
    $("#modal-logged-out").click(function () {
        $('#modal-logged-out').fadeToggle('fast');
    });
    $("#closeFavorite").click(function() {
    	e.preventDefault();
        $("#modal-save-favorite").hide();
    });
    // Close the modal box on blur
    $('html').click(function() {
        $('#modal-save-favorite').hide();
        $('#modal-logged-out').hide();
    });
    $('#modal-save-favorite, #favorite-star-png, #edit-favorite').click(function(e) {
        // Prevents the above from closing the modal when the modal is clicked.
        e.stopPropagation();
    });
    $('#save-favorite-notes-field').NobleCount('#characters-remaining',{
        // set up the char counter
        //on_negative: 'errortext',
        on_negative: function(t_obj, char_area, c_settings, char_rem){
            $('#characters-remaining').addClass("errortext");
            $('#saveFavorite').attr('disabled', 'disabled');
        },
        on_positive: function(t_obj, char_area, c_settings, char_rem){
            $('#characters-remaining').removeClass("errortext");
            $('#saveFavorite').removeAttr('disabled');
        },
        max_chars: '500'
    });
});

// Close the modal box if ESC is pressed.
$(document).keyup(function(e) {
    if (e.keyCode == "27") {
        $('#modal-save-favorite').hide();
        $('#modal-logged-out').hide();
    }
});

// Ajax functions for favorites form.
$(function() {
    $("#saveFavorite").click(function() {
        // validate and process form here
        var csrf   = $("input[name=csrfmiddlewaretoken]").val();
        var doc_id = $("input#id_doc_id").val();
        var name   = $("input#save-favorite-name-field").val();
        var notes  = $("textarea#save-favorite-notes-field").val();

        var dataString = 'csrf='+ csrf + '&doc_id=' + doc_id + '&notes=' + notes + '&name=' + name;
        //alert (dataString);
        $.ajax({
            type: "POST",
            url: "/favorite/create-or-update/",
            data: dataString,
            success: function() {
                // Hide the modal box
                $("#modal-save-favorite").toggle();

                // Fill in the star and reset its title attr
                $('#favorite-star-png').removeClass('favorite-off');
                $('#favorite-star-png').addClass('favorite-on');

                // Add the new favorites info to the sidebar.
                if (notes == ''){
                    notes = '(none)';
                }
                $('#sidebar-notes-text').text(notes);
                $('#sidebar-notes').show();

                $('#save-favorite-delete').removeClass('hidden');
                $('#save-favorite-title').text('Edit/delete this favorite');
            }
        });
        return false;
    });

    $("#save-favorite-delete").click(function() {
        // Send a post that deletes the favorite from the DB, and if successful
        // remove the notes from the sidebar, and toggle the star icon
        // to be blanked out.
        var csrf   = $("input[name=csrfmiddlewaretoken]").val();
        var doc_id = $("input#id_doc_id").val();
        var dataString = 'csrf=' + csrf + '&doc_id=' + doc_id;
        $.ajax({
            type: "POST",
            url: "/favorite/delete/",
            data: dataString,
            success: function() {
                // Hide the modal box
                $("#modal-save-favorite").toggle();
                // Empty the star and reset its titles
                $('#favorite-star-png').removeClass('favorite-on');
                $('#favorite-star-png').addClass('favorite-off');

                // Hide the sidebar
                $('#sidebar-notes').hide();

                // Hide the delete button again
                $('#save-favorite-delete').addClass('hidden');

                // Update the title in the modal box
                $('#save-favorite-title').text('Save a favorite');
            }
        });
        return false;
    });
});

// This is from https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#ajax
// Makes Django's anti-CSRF work.
$(document).ajaxSend(function(event, xhr, settings) {
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
    function sameOrigin(url) {
        // url could be relative or scheme relative or absolute
        var host = document.location.host; // host + port
        var protocol = document.location.protocol;
        var sr_origin = '//' + host;
        var origin = protocol + sr_origin;
        // Allow absolute or scheme relative URLs to same origin
        return (url == origin || url.slice(0, origin.length + 1) == origin + '/') ||
            (url == sr_origin || url.slice(0, sr_origin.length + 1) == sr_origin + '/') ||
            // or any other URL that isn't scheme relative or absolute i.e relative.
            !(/^(\/\/|http:|https:).*/.test(url));
    }
    function safeMethod(method) {
        return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
    }

    if (!safeMethod(settings.type) && sameOrigin(settings.url)) {
        xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
    }
});
