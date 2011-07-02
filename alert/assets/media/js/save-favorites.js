$(function() {
    $("#saveFavorite").click(function() {
        // validate and process form here
        var csrf   = $("input[name=csrfmiddlewaretoken]").val();
        var doc_id = $("input#id_doc_id").val();
        var notes  = $("textarea#save-favorite-text-area").val();
        var tags   = $("input#id_tags").val();

        var dataString = 'csrf='+ csrf + '&doc_id=' + doc_id + '&notes=' + notes + '&tags=' + tags;
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
                $('#favorite-star-png').attr('title', 'Edit/delete favorite');

                // Add the new favorites info to the sidebar.
                $('#sidebar-notes').text(notes);

                // Loop through the tags, and make some HTML from them.
                // This next line makes an array from the values of the tags,
                // while stripping out the word "Create"
                var tagTextArray = $('.token-input-token-facebook p').map(function() {
                    return $(this).text().split('Create: ').slice(-1);
                }).get();
                var tagsHTML = "";
                for (var i = 0; i < tagTextArray.length; i++ ){
                  tagsHTML = tagsHTML + "<li class='tag'><a class='tag' href='/search/tag/" +
                    tagTextArray[i] + "/'>" + tagTextArray[i] + "</a></li>";
                }
                $('#sidebar-tags').html(tagsHTML);
                $('#sidebar-tags-and-notes').show();
                $('#save-favorite-delete').removeClass('hidden');
                $('#save-favorite-title').text('Edit/delete this favorite');
            }
        });
        return false;
    });

    $("#save-favorite-delete").click(function() {
        // Send a post that deletes the favorite from the DB, and if successful
        // remove the notes and tags from the sidebar, and toggle the star icon
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
                $('#favorite-star-png').attr('title', 'Save favorite');

                // Hide the sidebar
                $('#sidebar-tags-and-notes').hide();

                // Hide the delete button again
                $('#save-favorite-delete').addClass('hidden');

                // Update the title in the modal box
                $('#save-favorite-title').text('Save as a favorite');
            }
        });
        return false;
    });
});
