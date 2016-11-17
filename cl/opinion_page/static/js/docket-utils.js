var picker = $("#actions-picker"),
    table_body = $('#document-table tbody');

// Do AJAX when modal is shown.
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
                    'html': 'Item not yet in our collection. Please download it using <a href="https://free.law/recap/" target="_blank">RECAP</a> and we will have it soon.'
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
    // Prepare for a different entry to be opened, by emptying the modal.
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
    if (item.filepath_local) {
        row.append($('<td>').append($('<a>', {
            'text': type + number_attr,
            'href': item.absolute_url
        })));
    } else {
        row.append($('<td>').text(type + number_attr))
    }

    row.append($('<td>').text(item.description || "Unknown Description"));
    var btn_attrs = {'text': "Download"},
        div_attrs = {'class': 'float-right btn-div'};
    if (item.filepath_local){
        $.extend(btn_attrs, {
            'href': "/" + item.filepath_local,
            'class': 'btn-primary btn'
        });
    } else {
        // Item not yet in CourtListener.
        if (item.pacer_url === '') {
            // We can't make the PACER URL for some reason. Show an error as a
            // tooltip on the button (we might have the description). Later,
            // we'll let people click to get the item.
            $.extend(btn_attrs, {
                'href': "#",
                'class': "btn btn-primary disabled"
            });
            $.extend(div_attrs, {
                'role': 'button',
                'data-toggle': "tooltip",
                'data-container': 'body',
                'title': 'Item not yet in our collection. Please download it using RECAP and we will have it soon.'
            });
        } else {
            $.extend(btn_attrs, {
                'href': item.pacer_url,
                'class': "btn btn-primary",
                'text': "Buy on PACER"
            });
        }
    }

    row.append($('<td>')
       .append($('<div>', div_attrs)
       .append($('<a>', btn_attrs))));

    row.appendTo('#document-table tbody');

    // Activate the tooltip.
    row.find('[data-toggle="tooltip"]').tooltip();
};

// Allow links in the docket to be clicked without triggering the modal.
$('.docket-entry a').on('click', function (ev) {
    ev.stopPropagation();
});
// Initialize tooltips on profile pages.
$('[data-toggle="tooltip"]').tooltip();

// Change sort order when the asc/desc buttons are clicked.
$("#sort-buttons :input").change(function () {
    this.closest("form").submit();
});
