function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie != '') {
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var cookie = jQuery.trim(cookies[i]);
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) == (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

function getDocketIdFromH1Tag() {
  const h1 = document.querySelector('h1[data-id]');
  return parseInt(h1.dataset.id);
}

function createListElement({ item }) {
  const { id, name, dockets, linkId } = item;

  const active = dockets.includes(getDocketIdFromH1Tag());
  const listItem = document.createElement("li");
  listItem.classList +=
    "list-group-item list-group-item-action d-flex align-items-center filterable";

  if (name.startsWith("Create Option:")) {
    listItem.textContent = name;
    listItem.setAttribute('style', 'cursor:default;')
    // add the createNewOption click handler
    listItem.addEventListener("click", (ev) => {
      ev.stopImmediatePropagation();
      const newTag = ev.target.textContent.replace("Create Option: ", "");
      console.log(`Creating new option "${newTag}"`);
      // fire POST event

      window.fetch("/api/rest/v3/tags/", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...csrfTokenHeader },
        body: JSON.stringify({
        // object (e.g., docket) identifier
          name: newTag,
        })
      })
      .then(res => res.json())
      .then((data) => {
        if (!data) return;
        // create the association
        window.fetch("/api/rest/v3/docket-tags/", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", ...csrfTokenHeader },
          body: JSON.stringify({
            tag: data.id,
            docket: getDocketIdFromH1Tag(),
          })
        })
        .then(res => res.json())
        .then(linkData => {
          // reset the textInput
          document.getElementById("labelFilterInput").value = "";
          // update the data in the hiddenDiv
          const hiddenDiv = document.getElementById("tagData");
          const oldData = JSON.parse(hiddenDiv.textContent);
          const newData = [
            ...oldData,
            // the association id should be the attached to the link
            { id: data.id, name: data.name, dockets: [getDocketIdFromH1Tag()], linkId: linkData.id }
          ];
          hiddenDiv.textContent = JSON.stringify(newData);
          // rebuild the list
          removeListElements();
          addListElements({ data: newData });
        })
      })
      .catch((err) => console.error(err))
    });
  } else {
      listItem.innerHTML = `
        <div class="form-check form-check-inline">
          <input type="checkbox" id=${linkId} value=${name} ${
        !!active && "checked"
      } class="form-check position-static ${active ? "checked" : ""}" data-tagid="${id}">
          <label class="ml-4 form-check-label text-capitalize" for="${name}">${name}</label>
        </div>
      `;
      
      createListClickHandler(listItem.querySelector('input'));

      listItem.addEventListener("click", (ev) => {
        // stop click from closing form
        ev.stopImmediatePropagation();
        // make click on listItem set the checkbox
        ev.currentTarget.querySelector("input").click();
      });
    }
  return listItem;
}

function createListClickHandler(input) {
  return input.addEventListener("click", (ev) => {
    ev.stopImmediatePropagation();
    // don't fire listItem handler

    // remove association if already checked
    if (input.hasAttribute("checked")) {
      console.log(`Removing ${input.value} from tags`);
      // fire POST to backend
      window
        .fetch(`/api/rest/v3/docket-tags/${input.id}/`, {
          method: "DELETE",
          headers: csrfTokenHeader,
          credentials: "include",
        })
        .then((res) => input.removeAttribute("checked"))
        .catch((err) => console.error(err));
    } else {
      // associate tag with object
      console.log(`Adding ${input.value} to tags`);
      // fire POST to backend
      window
        .fetch('/api/rest/v3/docket-tags/', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', ...csrfTokenHeader },
          body: JSON.stringify({
            tag: input.dataset.tagid,
            docket: getDocketIdFromH1Tag(),
          })
        })
        .then((res) => res.json())
        // update the id on the input to reflect the linkId
        .then(data => {
          input.setAttribute('id', data.id)
          input.setAttribute("checked", true)
        })
        .catch((err) => console.error(err));
    }
  });
}

function addListElements({ data }) {
  const docketId = getDocketIdFromH1Tag();
  // create the list elements and inject them before the last one
  if (data !== undefined && data.length > 0) {
    data.map((item) => {
      const list = document.querySelector("ul#list-group");
      const editItem = document.querySelector("a#editButton");
      const newItem = createListElement({ item });
      list.insertBefore(newItem, editItem);
    });
    // change the placeholder on the textInput if items exist
    document
      .getElementById("labelFilterInput")
      .setAttribute("placeholder", "Filter labels");
  }
  // add listener for onChange to all checkboxes
  // [...document.querySelectorAll('input[type="checkbox"]')].map((input) =>
  //   createListClickHandler(input)
  // );
}

function removeListElements() {
  [...document.querySelectorAll("li.filterable")].map((el) =>
    el.parentNode.removeChild(el)
  );
}

// script runtime start

// 0. set the CSRF token
const csrfTokenHeader = { 'X-CSRFToken': getCookie('csrftoken') };

window.onload = () => {
  // 1. remove the click listener from the static listItems
  // to prevent form from closing on click
  [...document.querySelectorAll("li.list-group-item")].map((node) => {
    return node.addEventListener("click", (e) => e.stopPropagation());
  });

  // 2. fetch the data from the backend and populate the list items
    window.fetch("/api/rest/v3/tags/", {
      method: "GET",
      headers: { "Content-Type": "application/json", ...csrfTokenHeader },
    })
    .then((res) => res.json())
    .then((tags) => {
      // fetch the associations
      window.fetch('/api/rest/v3/docket-tags/', {
        method: 'GET',
        headers: {'Content-Type': 'application/json', ...csrfTokenHeader }
      })
      .then(res => res.json())
      .then((resData) => {
        // create the new data
        const results = tags.results.map((tag) => {
          const linkData = resData.results.find((link) => {
            return link.tag === tag.id && link.docket === getDocketIdFromH1Tag();
          })
          return { ...tag, linkId: linkData?.id }
        })
        // stash the data in a hidden div
        const hiddenDiv = document.createElement("div");
        hiddenDiv.id = "tagData";
        hiddenDiv.style.visibility = "hidden";
        hiddenDiv.textContent = JSON.stringify(results);
        document.querySelector("body").appendChild(hiddenDiv);
        return results;
      })
      // iterate through the data to create the list Elements
      .then(associatedTags => addListElements({ data: associatedTags }))
    })
    .catch(err => console.log(err.message));

  // 3. add listener to the textInputSearch and change placeholder

  document.getElementById("labelFilterInput").addEventListener("keyup", (ev) => {
    const { value } = ev.target;
    // get the data from the hidden Div
    const oldData = JSON.parse(document.getElementById("tagData").textContent);
    // apply the filter
    const filtered = oldData.filter(({ name }) => {
      // don't use previous Create Option items
      if (name.startsWith('Create Option:')) return false
      return name.includes(value)
    });
    // remove the stale elements
    removeListElements();
    // inject the createOption listItem if no results found
    const data =
      filtered.length >= 1
        ? filtered
        : [{ id: '-1', name: `Create Option: ${capitalize(value)}`, dockets: [] }, ...filtered];

    addListElements({ data });
  });
}