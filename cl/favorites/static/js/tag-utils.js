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

// get the csrf token
const token = getCookie('csrftoken');

// if there's an h1 with a span tag in it
const isSingleTagView = document.querySelector('h1 > span.tag');

// find the "Untag this Item" options in the Tag_View page and bind
// click listeners to them
if (isSingleTagView) {
  const untagOptionButtons = [...document.querySelectorAll('li > a')].filter((a) =>
    a.textContent.includes('Untag this item')
  );
  untagOptionButtons.map((button) => {
    button.addEventListener('click', () => {
      fetch('/api/rest/v3/docket-tags/' + button.dataset.id + '/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': token },
      })
        .then((res) => {
          console.log('Docket-tag ' + button.dataset.id + ' deleted');
          // remove the docket from the tags page
          // button is contained in html as follows
          // li => div.dropdown.float-right => ul.dropdown-menu => li => button
          button.parentNode.parentNode.parentNode.parentNode.remove();
        })
        .catch((err) => console.log(err.message));
      return false;
    });
  });
}
