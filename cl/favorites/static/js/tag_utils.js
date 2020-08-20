// (name: String) => CsrfToken
function getCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie != "") {
    var cookies = document.cookie.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var cookie = jQuery.trim(cookies[i]);
      // Does this cookie string begin with the name we want?
      if (cookie.substring(0, name.length + 1) == name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// () => Int
function getDocketIdFromH1Tag() {
  const h1 = document.querySelector("h1[data-id]");
  return parseInt(h1.dataset.id);
}

//  interface Tag {
//    id: Int
//    name: String
//    dockets: Int[]
//    associationId: Int
//  }

// given a tag and the id of its association with the docket
// build the listItem to inject into the <ul> element
// (tag: Tag) => HTMLLiElement
function createListElement(tag) {
  // destructure tag contents
  const { id, name, dockets, associationId } = tag;

  // item is active if the item's docket array contains the current dockerId
  const active = dockets.includes(getDocketIdFromH1Tag());

  // create the listItem to be added to the DOM
  const listItem = document.createElement("li");

  // style the element using bs3 css
  listItem.classList.add(
    "d-flex",
    "align-items-center",
    "filterable",
    "list-group-item",
    "list-group-item-action"
  );

  // if the name is the create option, create a listItem
  // with a click handler that fires the POST to the server
  // and mutates the DOM in the callback
  if (name.startsWith("Create Option:")) {
    listItem.textContent = name;
    listItem.setAttribute("style", "cursor:default;");

    // add the createNewOption click handler
    listItem.addEventListener("click", (ev) => {
      // stop the click from closing the list
      ev.stopImmediatePropagation();

      // get the name of the new tag
      const name = ev.target.textContent.replace("Create Option: ", "");
      console.log(`Creating new option "${name}"`);

      // fire POST event
      window
        .fetch("/api/rest/v3/tags/", {
          method: "POST",
          headers: csrfTokenHeader,
          body: JSON.stringify({ name })
        })
        .then((res) => res.json())
        // after data returned, create the association
        .then((tagData) => {
          window
            .fetch("/api/rest/v3/docket-tags/", {
              method: "POST",
              headers: csrfTokenHeader,
              body: JSON.stringify({
                tag: tagData.id,
                docket: getDocketIdFromH1Tag()
              })
            })
            .then((res) => res.json())
            // once we have both the new tag and the association data
            // we reset the filterInput and update the stashed data
            .then((association) => {
              // reset the textInput
              document.getElementById("labelFilterInput").value = "";

              // get the data in the hiddenDev
              const hiddenDiv = document.getElementById("tagData");
              const oldData = JSON.parse(hiddenDiv.textContent);
              // create the object for the newTag
              const newTag = {
                id: tagData.id,
                name: tagData.name,
                dockets: [association.docket],
                associationId: association.id
              };
              const data = [...oldData, newTag];
              hiddenDiv.textContent = JSON.stringify(data);

              // rebuild the list
              removeListElements();
              addListElements({ data });
            })
            .catch((err) => console.error(err));
        })
        .catch((err) => console.error(err));
    });
  } else {
    // associationId will be undefined unless an association exists
    listItem.innerHTML = `
        <div class="form-check form-check-inline">
          <input type="checkbox" id=${associationId} value=${name} ${
      !!active && "checked"
    } class="form-check position-static ${
      active ? "checked" : ""
    }" data-tagid="${id}">
          <label class="ml-4 form-check-label" for="${name}">${name}</label>
        </div>
      `;

    // attach the clickHandler
    createListClickHandler(listItem.querySelector("input"));

    // make a click on the div click the checkbox
    listItem.addEventListener("click", (ev) => {
      // stop click from performing other actions
      ev.stopImmediatePropagation();
      // make click on listItem set the checkbox
      ev.currentTarget.querySelector("input").click();
    });
  }
  return listItem;
}

// attach the clickHandler to the target input
// (input: HtmlInputElement) => void;
function createListClickHandler(input) {
  return input.addEventListener("click", (ev) => {
    // don't fire listItem handler
    ev.stopImmediatePropagation();

    // remove association if already checked
    if (input.hasAttribute("checked")) {
      console.log(`Removing ${input.value} from tags`);
      // fire POST to backend
      window
        .fetch(`/api/rest/v3/docket-tags/${input.id}/`, {
          method: "DELETE",
          headers: csrfTokenHeader
        })
        // if successfully removed, uncheck tag
        .then((res) => input.removeAttribute("checked"))
        .catch((err) => console.error(err));
    } else {
      // associate tag with object
      console.log(`Adding ${input.value} to tags`);
      // fire POST to backend
      window
        .fetch("/api/rest/v3/docket-tags/", {
          method: "POST",
          headers: csrfTokenHeader,
          body: JSON.stringify({
            tag: input.dataset.tagid,
            docket: getDocketIdFromH1Tag()
          })
        })
        .then((res) => res.json())
        // update the id on the input to reflect the associationId
        // and set the tag to checked
        .then((association) => {
          input.setAttribute("id", association.id);
          input.setAttribute("checked", true);
        })
        .catch((err) => console.error(err));
    }
  });
}

// given data, create the listElements and inject
// them into the DOM
// ({ data }: { data: Tag[] }) => void;
function addListElements({ data }) {
  const docketId = getDocketIdFromH1Tag();
  if (data === undefined || data.length < 1) return;
  // create the list elements and inject them before the last one
  data.map((item) => {
    const list = document.querySelector("ul#list-group");
    const editButton = document.querySelector("a#editButton");
    const newItem = createListElement(item);
    // insert the new item before the edit button
    list.insertBefore(newItem, editButton);
  });
  // change the placeholder on the textInput if items exist
  document
    .getElementById("labelFilterInput")
    .setAttribute("placeholder", "Filter labels");
}

// removes list elements from the DOM
// () => void;
function removeListElements() {
  [...document.querySelectorAll("li.filterable")].map((el) =>
    el.parentNode.removeChild(el)
  );
}

// script start

// 0. set the CSRF token
const csrfTokenHeader = {
  "Content-Type": "application/json",
  "X-CSRFToken": getCookie("csrftoken")
};

window.onload = () => {
  // 1. check to see if the button is disabled - do nothing if it is
  const tagButton = document.querySelector('button#tagSelect');
  if (tagButton.disabled) return;

  // 2. remove the click listener from the static listItems
  // to prevent form from closing on click
  [...document.querySelectorAll("li.list-group-item")].map((node) => {
    return node.addEventListener("click", (e) => e.stopPropagation());
  });

  // 3. fetch the data from the backend and populate the list items
  window
    .fetch("/api/rest/v3/tags/", {
      method: "GET",
      headers: csrfTokenHeader
    })
    .then((res) => res.json())
    .then((tags) => {
      // fetch the associations
      window
        .fetch("/api/rest/v3/docket-tags/", {
          method: "GET",
          headers: csrfTokenHeader
        })
        .then((res) => res.json())
        .then((resData) => {
          // create the new data
          const results = tags.results.map((tag) => {
            const association = resData.results.find((assoc) => {
              return (
                assoc.tag === tag.id && assoc.docket === getDocketIdFromH1Tag()
              );
            });
            return { ...tag, associationId: association?.id };
          });
          // stash the data in a hidden div
          const hiddenDiv = document.createElement("div");
          hiddenDiv.id = "tagData";
          hiddenDiv.style.visibility = "hidden";
          hiddenDiv.textContent = JSON.stringify(results);
          document.querySelector("body").appendChild(hiddenDiv);
          return results;
        })
        // iterate through the data to create the list Elements
        .then((associatedTags) => addListElements({ data: associatedTags }));
    })
    .catch((err) => console.log(err.message));

  // 4. add listener to the textInputSearch and change placeholder

  document
    .getElementById("labelFilterInput")
    .addEventListener("keyup", (ev) => {
      const { value } = ev.target;
      // get the data from the hidden Div
      const oldData = JSON.parse(
        document.getElementById("tagData").textContent
      );
      // apply the filter
      const filtered = oldData.filter(({ name }) => {
        // don't use previous Create Option items
        if (name.startsWith("Create Option:")) return false;
        return name.includes(value);
      });
      // remove the stale elements
      removeListElements();
      // inject the createOption listItem if it is not an exact result
      const exactTagExists = filtered.find(({ name }) => name === value);
      const data = exactTagExists
        ? filtered
        : [
            {
              id: "-1",
              name: `Create Option: ${value}`,
              dockets: []
            },
            ...filtered
          ];

      addListElements({ data });
    });
};
