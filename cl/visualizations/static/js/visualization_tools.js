$(document).ready(function () {
    ////////////////////
    // Trash, Restore //
    ////////////////////
    $(".trash-button, .restore-button").click(function (e) {
        e.preventDefault();
        var button = $(this),
            id = button.data('id'),
            buttonIcon = button.find('i'),
            parentRow = button.closest('tr'),
            pageType,
            message;

        buttonIcon
            .removeClass("fa-trash-o")
            .addClass("fa-spinner fa-pulse");
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
        // Initialize tooltips on profile pages.
        $('[data-toggle="tooltip"]').tooltip()
    });

    /////////////////////
    // Share/privatize //
    /////////////////////
    $('.share-button').click(function(e){
        e.preventDefault();
        var button = $(this),
            id = button.data('id'),
            action = button.data('function'),
            buttonIcon = button.find('i'),
            privateLabel = $('span.private-label'),
            shareLabel = $('#share'),
            url = function () {
                if (action === 'share') {
                    return "/visualizations/scotus-mapper/share/"
                } else if (action === 'privatize') {
                    return '/visualizations/scotus-mapper/privatize/';
                }
            }(),
            message = function() {
                if (action === 'share'){
                    return "This page can be seen by anybody with the link!";
                } else if (action === 'privatize'){
                    return "This page can only be seen by you.";
                }
            }();

        buttonIcon
            .removeClass('fa-share-alt')
            .addClass('fa-spinner fa-pulse');
        $.ajax({
            method: "POST",
            url: url,
            data: {pk: id},
            success: function(){
                $('.bootstrap-growl').alert("close");
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
                if (action === "share"){
                    action = "privatize";
                    button.data('function', 'privatize');
                    privateLabel.addClass('hidden');
                    buttonIcon
                        .removeClass('fa-spinner fa-pulse')
                        .addClass('fa-lock');
                    shareLabel.text("Unshare");
                } else if (action === "privatize"){
                    action = "share";
                    button.data('function', 'share');
                    privateLabel.removeClass('hidden');
                    buttonIcon
                        .removeClass('fa-spinner fa-pulse')
                        .addClass('fa-share-alt');
                    shareLabel.text("Share");
                }
            },
            error: function(){
                if (action === 'share'){
                    buttonIcon
                        .removeClass("fa-spinner fa-pulse")
                        .addClass('fa-share-alt');
                } else if (action === 'privatize') {
                    buttonIcon
                        .removeClass("fa-spinner fa-pulse")
                        .addClass('fa-lock');
                }
                $.bootstrapGrowl(
                    "An error occurred. Please try again.",
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
    })
});
