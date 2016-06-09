$('#actions-picker').on('show.bs.modal', function (event) {
    var row = $(event.relatedTarget);
    var pk = row.data('docket-entry');

    $.ajax({
        method: "GET",
        url: "/docket-entry/" + pk + "/",
        success: function (data) {
            if (data.item_count > 0) {
                // Build the table
                $.each(data.documents, function (i, item) {
                    makeRow(item, "Entry ");
                });
                $.each(data.attachments, function (i, item) {
                    makeRow(item, "Attachment ");
                });
            } else {
                // No items in RECAP -- throw an error.
                $('#document-table tbody').append($('<tr>').append($('<td>', {
                    'colspan': '3',
                    'html': 'Item not yet in our collection. Please download using <a href="https://free.law/recap/" target="_blank">RECAP</a> and we will have it soon.'
                })));
            }

        },
        error: function () {
            $('#document-table tbody').append(
                $('<tr>').append(
                    $('<td>', {
                        'colspan': '3',
                        'text': "Oops! An error occurred. Please refresh " +
                        "the page and try again."
                    })
                ));
        }
    });
});

$('#actions-picker').on('hide.bs.modal', function (event) {
    // Prepare for a different entry to be opened.
    $('#document-table tbody').empty();
});

var makeRow = function (item, type) {
    var row = $('<tr>');
    var number_attr;
    if (type === 'Entry ') {
        number_attr = item.document_number;
    } else {
        number_attr = item.attachment_number;
    }
    row.append($('<td>').text(type + number_attr));

    if (item.filepath_local) {
        row.append($('<td>').text(item.description || "Unknown Description"));
        row.append($('<td>')
            .append($('<div>')
                .attr('class', 'float-right')
                .append(
                    $('<a>')
                        .attr({
                            'href': "/" + item.filepath_local,
                            'class': 'btn-primary btn'
                        })
                        .text("Download")
                )));
    } else {
        // Item not yet in CourtListener. For now, show an error.
        // Later, we'll let people click to get the item.
        row.append($('<td>', {
            'colspan': '3',
            'html': 'Item not yet in our collection. Please download using <a href="https://free.law/recap/" target="_blank">RECAP</a> and we will have it soon.'
        }));
    }

    row.appendTo('#document-table tbody');
};
