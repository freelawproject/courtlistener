

 document.addEventListener('DOMContentLoaded', function() {

    $(".dropdown-toggle").on('click', function(e){
            $(this).parent().toggleClass('open');
     })


    // {# Change tabs #}
    $(".tablinks").on("click", function () {
        $(".active").toggleClass("active")
    })

    // {# This is the all | none call to select all or none #}
    $("a[data-check]").on('click', function() {
      $("[data-checkbox='" + $(this).data('check') + "']").prop("checked", true).trigger("change");
    })

    $("a[data-uncheck]").on('click', function() {
      $("[data-checkbox='" + $(this).data('uncheck') + "']").prop("checked", false).trigger("change");
    })

    // {# The all or none options that have no associated checkboxes just need to check or uncheck everything#}
    $("a[data-shortcut]").on('click', function() {
      $("[data-panel='" + $(this).data('shortcut') + "'] input[type=checkbox]").prop("checked", true).trigger("change");
    })

    $("a[data-unshortcut]").on('click', function() {
      $("[data-panel='" + $(this).data('unshortcut') + "'] input[type=checkbox]").prop("checked", false).trigger("change");
    })


    // {#Checkbox is changing - check if it has an associated downstream check - if it does - check them#}
    $('input[type=checkbox]').change( function(){
      if ($(this).data('check') != null) {
        $("[data-checkbox='" + $(this).data('check') + "']").prop("checked", this.checked).trigger("change");
      }

      if ($(this).data('checkbox') != null) {
        var total = $("input[data-checkbox='" + $(this).data('checkbox') + "']").length
        var current = $("input[data-checkbox='" + $(this).data('checkbox') + "']:checked").length

        if (current == total) {
          $("[data-check='" + $(this).data('checkbox') + "']").prop("indeterminate", false)
           $("[data-check='" + $(this).data('checkbox') + "']").prop("checked", true)
        }
        else if (current == 0) {
          $("[data-check='" + $(this).data('checkbox') + "']").prop("indeterminate", false)
          $("[data-check='" + $(this).data('checkbox') + "']").prop("checked", false)
        }
        else {
          $("[data-check='" + $(this).data('checkbox') + "']").prop("indeterminate", true)
        }
      }

      refresh_tabs()

    });



  function refresh_tabs(){
      $(".tab-pane").each(function(){
          var all_count = $(this).find("input").length
          var court_count = $(this).find("input:checked").length
          var badge = $("span[data-name='" + $(this).data("badge") + "']")
          badge.text(court_count)
          badge.attr('data-value', court_count)
          badge.next("button").attr('data-value', court_count)

          var icon = $(badge).next().find("i")
          if (court_count == 0){
            icon.attr('class', 'fa fa-square-o')
          }
          else if (court_count == all_count){
            icon.attr('class', 'fa fa-check-square')
          }
          else {
            icon.attr('class', 'fa fa-minus-square')
          }

      })
  }


  $(document).on('click', "i[class='fa fa-square-o']", function() {
      $(this).attr('class', 'fa fa-check-square')
      $("[data-panel='" + $(this).data('tab') + "'] input[type=checkbox]").prop("checked", true).trigger("change");
  });

  $(document).on('click', "i[class='fa fa-check-square']", function() {
      $(this).attr('class', 'fa fa-square-o')
      $("[data-panel='" + $(this).data('tab') + "'] input[type=checkbox]").prop("checked", false).trigger("change");
  });

  $(document).on('click', "i[class='fa fa-minus-square']", function() {
      $(this).attr('class', 'fa fa-check-square')
      $("[data-panel='" + $(this).data('tab') + "'] input[type=checkbox]").prop("checked", true).trigger("change");
  });

  });
