document.addEventListener('alpine:init', () => {
  /**
   * Tags button of the docket page, for `cotton/docket_tags_button.html`.
   *
   * Saves what the user does in the combobox through the REST API: applies and
   * removes tags on the docket named by `data-docket`, and creates the tags
   * that don't exist yet. A choice that can't be saved is undone and its error
   * shown.
   */
  Alpine.data('docketTagsButton', () => {
    const TAG_NAME = /^[a-z0-9-]+$/;
    // Settles when every request made so far has finished.
    let queue = Promise.resolve();

    /** Sends JSON to the API and returns the parsed response. Throws on failure, with the API's answer in `body` when it gave one. */
    const sendJson = async (method, url, csrfToken, body) => {
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: body && JSON.stringify(body),
      });
      if (response.status === 204) return null;
      const data = await response.json();
      if (response.ok) return data;
      const error = new Error(`HTTP ${response.status}`);
      error.body = data;
      throw error;
    };

    return {
      // Id of the DocketTag applying each tag, keyed by tag id.
      associations: {},
      errorMessage: '',

      /** Loads the associations the template rendered. */
      init() {
        const script = this.$el.querySelector(':scope > script[type="application/json"]');
        this.associations = JSON.parse(script.textContent);
      },

      /** Moves focus to the search input when the popover opens. */
      focusSearch(event) {
        if (event.newState === 'open') event.target.querySelector('[role="combobox"]').focus();
      },

      /** Closes the popover, which returns focus to the button. */
      close() {
        this.$el.hidePopover();
      },

      /** Applies the selected tag to the docket. */
      attach({ detail }) {
        const { docket, docketTagsUrl, csrfToken } = this.$root.dataset;
        const tag = detail.option.value;
        this.save(async () => {
          const association = await sendJson('POST', docketTagsUrl, csrfToken, { tag, docket: Number(docket) });
          this.associations[tag] = association.id;
        }, detail.undo);
      },

      /** Removes the deselected tag from the docket. */
      detach({ detail }) {
        const { docketTagsUrl, csrfToken } = this.$root.dataset;
        const tag = detail.option.value;
        this.save(async () => {
          await sendJson('DELETE', `${docketTagsUrl}${this.associations[tag]}/`, csrfToken);
          delete this.associations[tag];
        }, detail.undo);
      },

      /** Creates a tag named as typed and selects it, which applies it. */
      create({ detail }) {
        const { tagsUrl, csrfToken, errorMessageInvalidName } = this.$root.dataset;
        if (!TAG_NAME.test(detail.label)) {
          this.errorMessage = errorMessageInvalidName;
          return;
        }
        this.save(async () => {
          const tag = await sendJson('POST', tagsUrl, csrfToken, { name: detail.label });
          detail.add({ value: tag.id, label: tag.name });
        });
      },

      /** Runs a request after the ones before it. If it fails, calls `undo` and shows the API's message about the request or the tag's name, or the default one. */
      save(request, undo) {
        const { errorMessageDefault } = this.$root.dataset;
        queue = queue.then(async () => {
          this.errorMessage = '';
          try {
            await request();
          } catch (error) {
            console.error('Could not save the tags:', error);
            this.errorMessage = error.body?.detail ?? error.body?.name?.[0] ?? errorMessageDefault;
            undo?.();
          }
        });
      },
    };
  });
});
