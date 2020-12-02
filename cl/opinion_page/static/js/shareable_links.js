

$("p").mouseup(function() {
    var url_path = document.URL
    var base_url = url_path.split("?highlight=")[0]
    $(".popover").remove()
    if (window.document.getSelection().toString().length > 1) {
      var goto = base_url + "?highlight=" +
            window.document.getSelection().toString().replace(/\s/g, '+')
            + "#highlight"
      var content = '<i id="popovertext">' + window.document.getSelection().toString() + "</i><a href=" +goto + "> Create shareable link</a>"
        $(this).popover({
        trigger: 'manual',
        title: 'Share',
        content: content,
        html: true,
        placement: 'left'
      }).popover('show');
    }
      var pg = $(this).prevAll().find(".star-pagination").last().text().replace("*", "")
      var cs = $("#cite-string").text().split(",")[0].trim() + " at " + pg
      $("#popovertext").html('" ' + window.document.getSelection().toString() + '"<br><br><b>' + cs + '</b><hr>' )
})
