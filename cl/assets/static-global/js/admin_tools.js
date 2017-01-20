$(document).ready(function () {

    // Block items
    $('.block-item').click(function(e){
        e.preventDefault();
        var button = $(this),
            id = button.data('id'),
            type = button.data('type'),
            url =  '/admin-tools/block-item/';
        $.ajax({
            method: 'POST',
            url: url,
            data: {"id": id, "type": type},
            success: function(){
                $('.bootstrap-growl').alert("close");
                $.bootstrapGrowl(
                    "Item blocked successfully.",
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
            error: function(){
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
        })

    });
});
