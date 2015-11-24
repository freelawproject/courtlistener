$(document).ready(function () {
    $(".trash-button, .restore-button").click(function (event) {
        event.preventDefault();
        var button = $(this),
            id = button.data('id'),
            buttonIcon = button.find('i'),
            parentRow = button.closest('tr'),
            pageType,
            message;

        buttonIcon.removeClass("fa-trash-o");
        buttonIcon.addClass("fa-spinner fa-pulse");
        if (window.location.href.indexOf("deleted") >= 0){
            // We're on the deleted page, trying to restore.
            pageType = "trash";
        } else {
            pageType = "active";
        }

        $.ajax({
            method: "POST",
            url: "/visualizations/scotus-mapper" + (pageType == 'trash' ? "/restore/" : "/delete/"),
            data: {pk: id},
            success: function () {
                $('.bootstrap-growl').alert("close");
                parentRow.fadeOut('slow');
                if (pageType == "trash") {
                    message = "Your item was restored successfully."
                } else {
                    message = "Your item was moved to the trash."
                }
                $.bootstrapGrowl(
                    message,
                    {
                        type: "success",
                        align: "center",
                        width: "auto",
                        delay: 2000,
                        allow_dismiss: false,
                        offset: {from: 'top', amount: 80}
                    }
                );
            },
            error: function () {
                buttonIcon.removeClass("fa-spinner fa-pulse");
                buttonIcon.addClass("fa-trash-o");
                if (pageType == "trash") {
                    message = "An error occurred. Unable to restore your item."
                } else {
                    message = "An error occurred. Unable to move your item to the trash."
                }
                $.bootstrapGrowl(
                    message,
                    {
                        type: "danger",
                        align: "center",
                        width: "auto",
                        delay: 2000,
                        allow_dismiss: false,
                        offset: {from: 'top', amount: 80}
                    }
                );
            }
        });
    });
    $(function () {
        // Initialize tooltips on this page.
        $('[data-toggle="tooltip"]').tooltip()
    })
});
