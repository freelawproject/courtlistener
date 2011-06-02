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
                // Fill in the star!
                $('#favorite-star-png').removeClass('favorite-off');
                $('#favorite-star-png').addClass('favorite-on');

                // Add the new favorites info to the sidebar.
                $('#sidebar-notes').text(notes);

                // Loop through the tags, and make some HTML from them.
                // This next line makes an array from the values of the tags,
                // while stripping out the word "Create"
                var tagTextArray = $('.token-input-token-facebook p').map(function() {return $(this).text().split('Create: ').slice(-1); }).get();
                var tagsHTML = "";
                for (var i = 0; i < tagTextArray.length; i++ ){
                  tagsHTML = tagsHTML + "<li class='tag'><a class='tag' href='/search/tag/" +
                    tagTextArray[i] + "/'>" + tagTextArray[i] + "</a></li>";
                }
                $('#sidebar-tags').html(tagsHTML);
            }
        });
        return false;
    });
});
