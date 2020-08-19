function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// TO DO: need mike input
function extractObjectIds() {
  // fetch object ids and return array of objects
  // [{ type: "docket", id: '1234'}, {type: 'opinion', id: '5678' }]
  return [];
}

function createListElement({ id, label, active }) {
  const listItem = document.createElement("li");
  listItem.classList +=
    "list-group-item list-group-item-action d-flex align-items-center filterable";

  if (label.startsWith("Create Option:")) {
    listItem.textContent = label;

    // add the createNewOption click handler
    listItem.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const newTag = ev.target.textContent.replace("Create Option: ", "");
      console.log(`Creating new option "${newTag}"`);
      // fire POST event

      // in production, use fetch
      // window.fetch("/tags/new", {
      // method: "POST",
      // credentials: 'include',
      // headers: { "Content-Type": "application/json" },
      // body: JSON.stringify({
      // object (e.g., docket) identifier
      // objectId: "1234",
      // tag: {
      // label: newTag,
      // active: true
      // }
      // })
      // })
      // .then(res => res.json())

      // in development, use mock data
      Promise.resolve({ id: "-1000", label: newTag, active })
        .then((data) => {
          if (!data) return;
          // reset the textInput
          document.getElementById("labelFilterInput").value = "";
          // update the data in the hiddenDiv
          const hiddenDiv = document.getElementById("tagData");
          const oldData = JSON.parse(hiddenDiv.textContent);
          const newData = [
            ...oldData,
            { id: data.id, label: data.label, active: data.active }
          ];
          hiddenDiv.textContent = JSON.stringify(newData);
          // rebuild the list
          removeListElements();
          addListElements({ data: newData });
        })
        .catch((err) => console.error(err));
    });
  } else {
    listItem.innerHTML = `
      <div class="form-check form-check-inline">
        <input type="checkbox" id=${id} value=${label} ${
      !!active && "checked"
    } class="form-check position-static ${active ? "checked" : ""}">
        <label class="ml-4 form-check-label text-capitalize" for="${label}">${label}</label>
      </div>
    `;
    listItem.addEventListener("click", (ev) => {
      // stop click from closing form
      ev.stopPropagation();
      // make click on listItem set the checkbox
      ev.currentTarget.querySelector("input").click();
    });
  }
  return listItem;
}

function createListClickHandler(input) {
  return input.addEventListener("click", (ev) => {
    // don't fire listItem handler
    ev.stopPropagation();

    // create the postPayload
    const fetchOptions = {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        // object (e.g., docket) identifier
        objectId: extractObjectIds(),
        // tag identifier
        tagId: input.id
      })
    };
    // remove association if already checked
    if (input.hasAttribute("checked")) {
      console.log(`Removing ${input.value} from tags`);
      // fire POST to backend
      window
        .fetch("/tags/unlink", fetchOptions)
        .then((res) => input.removeAttribute("checked"))
        .catch((err) => console.error(err));
    } else {
      // associate tag with object
      console.log(`Adding ${input.value} to tags`);
      // fire POST to backend
      window
        .fetch("/tags/link", fetchOptions)
        .then((res) => input.setAttribute("checked", true))
        .catch((err) => console.error(err));
    }
  });
}

function insertNewListElement(item) {
  const list = document.querySelector("ul.list-group");
  const editItem = document.querySelector("a#editButton");
  list.insertBefore(createListElement(item), editItem);
}

function addListElements({ data }) {
  // create the list elements and inject them before the last one

  if (data !== undefined && data.length > 0) {
    data.forEach((item) => insertNewListElement(item));
    // change the placeholder on the textInput if items exist
    document
      .getElementById("labelFilterInput")
      .setAttribute("placeholder", "Filter labels");
  }
  // add listener for onChange to all checkboxes
  [...document.querySelectorAll('input[type="checkbox"]')].map((input) =>
    createListClickHandler(input)
  );
}

function removeListElements() {
  [...document.querySelectorAll("li.filterable")].map((el) =>
    el.parentNode.removeChild(el)
  );
}

// script runtime start

// 1. remove the click listener from the static listItems
// to prevent form from closing on click
[...document.querySelectorAll("li.list-group-item")].map((node) => {
  return node.addEventListener("click", (e) => e.stopPropagation());
});

// 2. fetch the data from the backend and populate the list items

// in production, use window.fetch
// window.fetch("/tags/", {
// method: "GET",
// credentials: 'include',
// headers: { "Content-Type": "application/json" },
// })
// .then(res => res.json())

// in development, mock fetch call (returns promise)
Promise.resolve([
  { id: "1", label: "label4", active: true },
  { id: "2", label: "label5", active: false },
  { id: "3", label: "label6", active: undefined }
]).then((res) => {
  // stash the data in a hidden div
  const hiddenDiv = document.createElement("div");
  hiddenDiv.id = "tagData";
  hiddenDiv.style.visibility = "hidden";
  hiddenDiv.textContent = JSON.stringify(res);
  document.querySelector("body").appendChild(hiddenDiv);
  // iterate through the data to create the list Elements
  addListElements({ data: res });
});

// 3. add listener to the textInputSearch and change placeholder

document.getElementById("labelFilterInput").addEventListener("keyup", (ev) => {
  const { value } = ev.target;
  // get the data from the hidden Div
  const oldData = JSON.parse(document.getElementById("tagData").textContent);
  // apply the filter
  const filtered = oldData.filter(({ label }) => label.includes(value));

  // remove the stale elements
  removeListElements();
  // inject the createOption listItem if no results found
  const data =
    filtered.length >= 1
      ? filtered
      : [{ label: `Create Option: ${capitalize(value)}` }, ...filtered];
  addListElements({ data });
});
