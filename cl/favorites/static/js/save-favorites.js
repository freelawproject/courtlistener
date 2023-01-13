$(document).ready(function () {
  $('#closeFavorite').on("click", function (event) {
    event.preventDefault();
    $('#modal-save-favorite').modal('hide');
  });
  $('#modal-logged-out').on("click", function () {
    $('#modal-logged-out').modal('hide');
  });
  $('#save-favorite-notes-field').NobleCount('#characters-remaining', {
    // set up the char counter
    max_chars: '500'
  });
});

// Ajax functions for favorites form.
$(function () {
  $('#saveFavorite').on("click", function () {
    // validate and process form here
    let favorite_id = $('#modal-save-favorite').data('id'),
      cluster_id = $('input#id_cluster_id').val(),
      audio_id = $('input#id_audio_id').val(),
      docket_id = $('input#id_docket_id').val(),
      recap_doc_id = $('input#id_recap_doc_id').val(),
      name = $('input#save-favorite-name-field').val(),
      notes = $('textarea#save-favorite-notes-field').val();
    $.ajax({
      method: 'POST',
      url: '/favorite/create-or-update/',
      data: {
        cluster_id: cluster_id,
        audio_id: audio_id,
        docket_id: docket_id,
        recap_doc_id: recap_doc_id,
        notes: notes,
        name: name
      },
      success: function () {
        // Hide the modal box
        $('#modal-save-favorite').modal('hide');

        // Fill in the star and reset its title attr
        $('#favorites-star')
          .removeClass('btn-success')
          .addClass('btn-danger');
        // Toggle the favorite text button
        $('#favorites-star span').text('Edit Note');

        // Add the new favorites info to the sidebar and favorites page.
        if (notes == '') {
          notes = '(none)';
        }
        $('#sidebar-notes-text, #notes-' + favorite_id).text(notes);
        $('#sidebar-notes').show();
        $('#name-' + favorite_id + ' a').text(name);
        $('#data-store-' + favorite_id)
          .data('name', name)
          .data('notes', notes);

        $('#save-favorite-delete').removeClass('hidden');
        $('#save-favorite-title').text('Edit This favorite');
      }
    });
    return false;
  });

  $('#save-favorite-delete').on("click", function (event) {
    event.preventDefault();
    // Send a post that deletes the favorite from the DB, and if successful
    // remove the notes from the sidebar; toggle the star icon.
    var favorite_id = $('#modal-save-favorite').data('id'),
      cluster_id = $('input#id_cluster_id').val(),
      audio_id = $('input#id_audio_id').val(),
      docket_id = $('input#id_docket_id').val(),
      recap_doc_id = $('input#id_recap_doc_id').val(),
      dataString = `&cluster_id=${cluster_id}&audio_id=${audio_id}` +
        `&docket_id=${docket_id}&recap_doc_id=${recap_doc_id}`;
    $.ajax({
      type: 'POST',
      url: '/favorite/delete/',
      data: dataString,
      success: function () {
        // Hide the modal box
        $('#modal-save-favorite').modal('hide');
        // Empty the star and reset its titles
        $('#favorites-star')
          .removeClass('btn-danger')
          .addClass('btn-success');
        // Toggle the favorite text button
        $('#favorites-star span').text('Add Note');

        // Hide the sidebar
        $('#sidebar-notes').hide();

        // Hide the row on the faves page
        var fave_row = $('#favorite-row-' + favorite_id);
        if (fave_row.length > 0) {
          // It's a favorites page
          fave_row.hide();
        } else {
          // Hide the delete button again
          $('#save-favorite-delete').addClass('hidden');

          // Update the title in the modal box
          $('#save-favorite-title').text('Save a favorite');
        }
      }
    });
    return false;
  });
});
