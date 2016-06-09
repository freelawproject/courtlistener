var picker = $("#actions-picker"),
    table_body = $('#document-table tbody');

picker.on('show.bs.modal', function (event) {
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
                table_body.append($('<tr>').append($('<td>', {
                    'colspan': '3',
                    'html': 'Item not yet in our collection. Please download using <a href="https://free.law/recap/" target="_blank">RECAP</a> and we will have it soon.'
                })));
            }

        },
        error: function () {
            table_body.append(
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

picker.on('hide.bs.modal', function (event) {
    // Prepare for a different entry to be opened.
    table_body.empty();
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
    row.append($('<td>').text(item.description || "Unknown Description"));
    var btn_attrs = {'text': "Download"},
        div_attrs = {'class': 'float-right'};
    if (item.filepath_local){
        $.extend(btn_attrs, {
            'href': "/" + item.filepath_local,
            'class': 'btn-primary btn'
        });
    } else {
        // Item not yet in CourtListener. For now, show an error as a tooltip on
        // the button (we might have the description). Later, we'll let people
        // click to get the item.
        $.extend(btn_attrs, {
            'href': "#",
            'class': "btn-primary btn disabled"
        });
        $.extend(div_attrs, {
            'role': 'button',
            'data-toggle': "tooltip",
            'data-container': 'body',
            'title': 'Item not yet in our collection. Please download using RECAP and we will have it soon.'
        });
    }

    row.append($('<td>')
       .append($('<div>', div_attrs)
       .append($('<a>', btn_attrs))));

    row.appendTo('#document-table tbody');

    // Activate the tooltip.
    row.find('[data-toggle="tooltip"]').tooltip();
};


