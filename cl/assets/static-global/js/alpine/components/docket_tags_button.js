document.addEventListener('alpine:init', () => {
  /**
   * Tags button of the docket page, for `cotton/docket_tags_button.html`.
   *
   * Connects the combobox to the REST API: searches the user's tags for it,
   * applies and removes them on the docket named by `data-docket`, and creates
   * the ones that don't exist yet. A choice that can't be saved is undone and
   * its error shown.
   */
  Alpine.data('docketTagsButton', () => {
    const TAG_NAME = /^[a-z0-9-]+$/;
    // Settles when every request made so far has finished.
    let queue = Promise.resolve();

    /** Calls the API and returns the parsed response. Throws on failure, with the HTTP `status` and, when the API gave one, its answer in `body`. */
    const callApi = async (url, { method = 'GET', csrfToken, body, signal } = {}) => {
      const response = await fetch(url, {
        method,
        headers: csrfToken && { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: body && JSON.stringify(body),
        signal,
      });
      if (response.status === 204) return null;
      const data = await response.json().catch(() => null);
      if (response.ok) return data;
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      error.body = data;
      throw error;
    };

    return {
      // Id of the DocketTag applying each tag, keyed by tag id.
      associations: {},
      errorMessage: '',

      /** Loads the associations the template rendered. */
      init() {
        const script = this.$el.querySelector(':scope > template[data-associations]').content.querySelector('script');
        this.associations = JSON.parse(script.textContent);
      },

      /** Runs when the popover opens or closes: moves focus to the search input on open and drops the error on close. */
      toggled(event) {
        if (event.newState === 'open') event.target.querySelector('[role="combobox"]').focus();
        else this.errorMessage = '';
      },

      /** Closes the popover from Escape, which returns focus to the button. Leaves it open while an input method is composing. */
      close(event) {
        if (!event.isComposing) this.$el.hidePopover();
      },

      /** Answers the combobox's search with a page of the user's tags whose name starts with the typed text. */
      async search({ detail }) {
        const { tagsUrl, user, errorMessageDefault } = this.$root.dataset;
        const params = new URLSearchParams({
          user,
          name__istartswith: detail.query,
          order_by: 'name',
          fields: 'id,name',
          page: detail.page,
        });
        try {
          const page = await callApi(`${tagsUrl}?${params}`, { signal: detail.signal });
          const options = page.results.map((tag) => ({ value: tag.id, label: tag.name }));
          detail.respond(options, { hasMore: Boolean(page.next) });
        } catch (error) {
          if (error.name !== 'AbortError') detail.fail(error.body?.detail ?? errorMessageDefault);
        }
      },

      /** Applies the selected tag to the docket. A tag that is still applied counts as applied. */
      attach({ detail }) {
        const { docket, docketTagsUrl, csrfToken } = this.$root.dataset;
        const tag = detail.option.value;
        this.errorMessage = '';
        this.save(async () => {
          if (this.associations[tag] !== undefined) return;
          const association = await callApi(docketTagsUrl, { method: 'POST', csrfToken, body: { tag, docket: Number(docket) } });
          this.associations[tag] = association.id;
        }, detail.undo);
      },

      /** Removes the deselected tag from the docket. A tag that isn't applied, or no longer is, counts as removed. */
      detach({ detail }) {
        const { docketTagsUrl, csrfToken } = this.$root.dataset;
        const tag = detail.option.value;
        this.errorMessage = '';
        this.save(async () => {
          const association = this.associations[tag];
          if (association === undefined) return;
          try {
            await callApi(`${docketTagsUrl}${association}/`, { method: 'DELETE', csrfToken });
          } catch (error) {
            if (error.status !== 404) throw error;
          }
          delete this.associations[tag];
        }, detail.undo);
      },

      /** Creates a tag named as typed and selects it, which applies it. */
      create({ detail }) {
        const { tagsUrl, csrfToken, errorMessageInvalidName } = this.$root.dataset;
        this.errorMessage = '';
        if (!TAG_NAME.test(detail.label)) {
          this.errorMessage = errorMessageInvalidName;
          return;
        }
        this.save(async () => {
          const tag = await callApi(tagsUrl, { method: 'POST', csrfToken, body: { name: detail.label } });
          detail.add({ value: tag.id, label: tag.name });
        });
      },

      /** Runs a request after the ones before it. If it fails, calls `undo` and shows the API's message about the request or the tag's name, or the default one. */
      save(request, undo) {
        const { errorMessageDefault } = this.$root.dataset;
        queue = queue.then(async () => {
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
