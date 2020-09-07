// function to extract csrf token from cookie
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) === name + '=') {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

console.log('window loaded');
// get the csrf token
const token = getCookie('csrftoken');
// if it is a tags page, attach event listener to the delete button
const hasH1ForTagsPage = [...document.querySelectorAll('h1')].find((h1) => h1.textContent.includes('Your tags'));

if (hasH1ForTagsPage) {
  const deleteButtons = [...document.querySelectorAll('button.delete-tag-button')];
  deleteButtons.map((button) => {
    button.addEventListener('click', () => {
      console.log('click');
      fetch('/api/rest/v3/tags/' + button.dataset.id + '/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': token },
      })
        .then((res) => {
          console.log('Tag ' + button.dataset.id + ' deleted');
          // button is in a td container in a tr
          // remove the tr if successful
          button.parentNode.parentNode.remove();
        })
        .catch((err) => console.log(err.message));
    });
  });
}
