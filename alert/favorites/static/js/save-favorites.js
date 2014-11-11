$(document).ready(function() {
    $("#closeFavorite").click(function (event) {
        event.preventDefault();
        $("#modal-save-favorite").modal('hide');
    });
    $("#modal-logged-out").click(function () {
        $('#modal-logged-out').modal('hide');
    });
    $('#save-favorite-notes-field').NobleCount('#characters-remaining',{
        // set up the char counter
        on_negative: function(t_obj, char_area, c_settings, char_rem){
            $('#characters-remaining').addClass("badge badge-red");
            $('#saveFavorite').attr('disabled', 'disabled');
        },
        on_positive: function(t_obj, char_area, c_settings, char_rem){
            $('#characters-remaining').removeClass("badge badge-red");
            $('#saveFavorite').removeAttr('disabled');
        },
        max_chars: '500'
    });
});

// Ajax functions for favorites form.
$(function() {
    $("#saveFavorite").click(function() {
        // validate and process form here
        var csrf     = $("input[name=csrfmiddlewaretoken]").val();
        var favorite_id = $("#modal-save-favorite").data("id");
        var doc_id   = $("input#id_doc_id").val();
        var audio_id = $("input#id_audio_id").val();
        var name     = $("input#save-favorite-name-field").val();
        var notes    = $("textarea#save-favorite-notes-field").val();
        var dataString = 'csrf=' + csrf +
                         '&doc_id=' + doc_id +
                         '&audio_id=' + audio_id +
                         '&notes=' + notes +
                         '&name=' + name;
        //alert (dataString);
        $.ajax({
            type: "POST",
            url: "/favorite/create-or-update/",
            data: dataString,
            success: function() {
                // Hide the modal box
                $("#modal-save-favorite").modal('hide');

                // Fill in the star and reset its title attr
                $('#favorites-star').removeClass('gray fa-star-o bold');
                $('#favorites-star').addClass('gold fa-star');

                // Add the new favorites info to the sidebar and favorites page.
                if (notes == ''){
                    notes = '(none)';
                }
                $('#sidebar-notes-text, #notes-' + favorite_id).text(notes);
                $('#sidebar-notes').show();
                $("#name-" + favorite_id + " a").text(name);
                $("#data-store-" + favorite_id).data("name", name);
                $("#data-store-" + favorite_id).data("notes", notes);

                $('#save-favorite-delete').removeClass('hidden');
                $('#save-favorite-title').text('Edit This favorite');
            }
        });
        return false;
    });

    $("#save-favorite-delete").click(function(event) {
        event.preventDefault();
        // Send a post that deletes the favorite from the DB, and if successful
        // remove the notes from the sidebar; toggle the star icon.
        var csrf        = $("input[name=csrfmiddlewaretoken]").val();
        var favorite_id = $("#modal-save-favorite").data("id");
        var doc_id      = $("input#id_doc_id").val();
        var audio_id    = $("input#id_audio_id").val();
        var dataString = 'csrf=' + csrf +
                         '&doc_id=' + doc_id +
                         '&audio_id=' + audio_id;
        $.ajax({
            type: "POST",
            url: "/favorite/delete/",
            data: dataString,
            success: function() {
                // Hide the modal box
                $("#modal-save-favorite").modal('hide');
                // Empty the star and reset its titles
                $('#favorites-star').removeClass('gold fa-star');
                $('#favorites-star').addClass('gray fa-star-o bold');

                // Hide the sidebar
                $('#sidebar-notes').hide();

                // Hide the row on the faves page
                var fave_row = $('#favorite-row-' + favorite_id);
                if (fave_row.length > 0){
                    // It's a favorites page
                    fave_row.hide();
                } else {
                    // Hide the delete button again
                    $('#save-favorite-delete').addClass('hidden');

                    // Update the title in the modal box
                    $('#save-favorite-title').text('Save a favorite');
                }
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
