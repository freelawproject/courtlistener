
$("p").mouseup(function() {
    var url_path = document.URL
    var base_url = url_path.split("?highlight=")[0]
    $(".popover").remove()
    if (window.document.getSelection().toString().length > 1) {
      var goto = base_url + "?highlight=" +
            window.document.getSelection().toString().replace(/\s/g, '+')
            + "#highlight"
      $(this).popover({
        trigger: 'manual',
        title: 'Share',
        content: '<b>' + window.document.getSelection().toString() + "</b><br><hr><a href=" +goto + "> Create shareable link</a>",
        html: true,
        placement: 'left'
      }).popover('show');
    }
})
