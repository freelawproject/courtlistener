document.addEventListener('htmx:beforeRequest', function () {
  // If the mobile error message is currently visible, adds the 'hidden' class
  // to hide it.
  let mobileErrorMessage = document.getElementById('mobile-export-csv-error');
  if (!mobileErrorMessage.classList.contains('hidden')) {
    mobileErrorMessage.classList.add('hidden');
  }

  // If the desktop error message is currently visible, adds the 'hidden' class
  // to hide it.
  let desktopErrorMessage = document.getElementById('export-csv-error');
  if (!desktopErrorMessage.classList.contains('hidden')) {
    desktopErrorMessage.classList.add('hidden');
  }
});

document.addEventListener('htmx:beforeOnLoad', function (event) {
  // Get the XMLHttpRequest object from the event details
  const xhr = event.detail.xhr;
  if (xhr.status == 200) {
    const response = xhr.response;
    // Extract the filename from the Content-Disposition header and get
    //the MIME type from the Content-Type header
    const filename = xhr.getResponseHeader('Content-Disposition').split('=')[1];
    const mimetype = xhr.getResponseHeader('Content-Type');

    // Prepare a link element for a file download
    // Create a hidden link element for download
    const link = document.createElement('a');
    link.style.display = 'none';

    // Create a Blob object containing the response data with the correct
    // MIME type and generate a temporary URL for it
    const blob = new Blob([response], { type: mimetype });
    const url = window.URL.createObjectURL(blob);

    // Set the link's attributes for download
    link.href = url;
    link.download = filename.replaceAll('"', '');

    // It needs to be added to the DOM so it can be clicked
    document.body.appendChild(link);
    link.click();

    // Release the temporary URL after download (for memory management)
    window.URL.revokeObjectURL(url);
  } else {
    // If the request failed, show the error messages
    let mobileErrorMessage = document.getElementById('mobile-export-csv-error');
    mobileErrorMessage.classList.remove('hidden');

    let desktopErrorMessage = document.getElementById('export-csv-error');
    desktopErrorMessage.classList.remove('hidden');
  }
});
