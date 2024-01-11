$(document).ready(function () {
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
});
