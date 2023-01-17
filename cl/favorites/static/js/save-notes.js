$(document).ready(function () {
  $('#closeNote').on("click", function (event) {
    event.preventDefault();
    $('#modal-save-note').modal('hide');
  });
  $('#modal-logged-out').on("click", function () {
    $('#modal-logged-out').modal('hide');
  });
  $('#save-note-notes-field').NobleCount('#characters-remaining', {
    // set up the char counter
    max_chars: '500'
  });
});

// Ajax functions for notes form.
$(function () {
  $('#saveNote').on("click", function () {
    // validate and process form here
    let note_id = $('#modal-save-note').data('id'),
      cluster_id = $('input#id_cluster_id').val(),
      audio_id = $('input#id_audio_id').val(),
      docket_id = $('input#id_docket_id').val(),
      recap_doc_id = $('input#id_recap_doc_id').val(),
      name = $('input#save-note-name-field').val(),
      notes = $('textarea#save-note-notes-field').val();
    $.ajax({
      method: 'POST',
      url: '/notes/create-or-update/',
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
        $('#modal-save-note').modal('hide');

        // Fill in the star and reset its title attr
        $('#add-note-button')
          .removeClass('btn-success')
          .addClass('btn-warning');
        // Toggle the note text button
        $('#add-note-button span').text('Edit Note');

        // Add the new notes info to the sidebar and notes page.
        if (notes == '') {
          notes = '(none)';
        }
        $('#sidebar-notes-text, #notes-' + note_id).text(notes);
        $('#sidebar-notes').show();
        $('#name-' + note_id + ' a').text(name);
        $('#data-store-' + note_id)
          .data('name', name)
          .data('notes', notes);

        $('#save-note-delete').removeClass('hidden');
        $('#save-note-title').text('Edit This note');
      }
    });
    return false;
  });

  $('#save-note-delete').on("click", function (event) {
    event.preventDefault();
    // Send a post that deletes the note from the DB, and if successful
    // remove the notes from the sidebar; toggle the star icon.
    var note_id = $('#modal-save-note').data('id'),
      cluster_id = $('input#id_cluster_id').val(),
      audio_id = $('input#id_audio_id').val(),
      docket_id = $('input#id_docket_id').val(),
      recap_doc_id = $('input#id_recap_doc_id').val(),
      dataString = `&cluster_id=${cluster_id}&audio_id=${audio_id}` +
        `&docket_id=${docket_id}&recap_doc_id=${recap_doc_id}`;
    $.ajax({
      type: 'POST',
      url: '/notes/delete/',
      data: dataString,
      success: function () {
        // Hide the modal box
        $('#modal-save-note').modal('hide');
        // Empty the star and reset its titles
        $('#add-note-button')
          .removeClass('btn-warning')
          .addClass('btn-success');
        // Toggle the note text button
        $('#add-note-button span').text('Add Note');

        // Hide the sidebar
        $('#sidebar-notes').hide();

        // Hide the row on the notes page
        var note_row = $('#note-row-' + note_id);
        if (note_row.length > 0) {
          // It's a notes page
          note_row.hide();
        } else {
          // Hide the delete button again
          $('#save-note-delete').addClass('hidden');

          // Update the title in the modal box
          $('#save-note-title').text('Save a note');
        }
      }
    });
    return false;
  });
});
