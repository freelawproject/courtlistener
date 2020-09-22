import React, { useState } from 'react';
import { Button, Modal } from 'react-bootstrap';
import { queryCache, useMutation, usePaginatedQuery } from 'react-query';
import TagListInner from './TagListInner';
import { appFetch } from './_fetch';
import { Tag, UserState } from './_types';
import { useForm } from 'react-hook-form';

type Inputs = {
  example: string;
  exampleRequired: string;
};

const TagList: React.FC<UserState> = ({ userId, userName, isPageOwner }) => {
  const [page, setPage] = React.useState(1);

  // Factor out this, putTags, and deleteTags
  const getTags = React.useCallback(
    async (key: string, page = 1) =>
      await appFetch(`/api/rest/v3/tags/?user=${userId}&page=${page}&page_size=50&order_by=name`),
    []
  );

  const checktagByNameAndId = React.useCallback(
    // Check if a tag already exists with a given name excluding the one we
    // know exists.
    async (name: string, id: string) => await appFetch(`/api/rest/v3/tags/?user=${userId}&name=${name}&id!=${id}`),
    []
  );

  const putTag = React.useCallback(
    async (tag: object) =>
      await appFetch(`/api/rest/v3/tags/${tag.id}/`, {
        method: 'PUT',
        body: { ...tag },
      }),
    []
  );

  const deleteTag = React.useCallback(
    async (id: number) =>
      await appFetch(`/api/rest/v3/tags/${id}/`, {
        method: 'DELETE',
      }),
    []
  );

  const { isLoading, isError, error, resolvedData, latestData, isFetching } = usePaginatedQuery(
    ['tags', page],
    getTags
  );

  const [updateTag] = useMutation(putTag, {
    onSuccess: (data, variables) => {
      queryCache.setQueryData(['tags', page], (old: any) => {
        console.log(data, old);
        // A list of the old items filtered to remove the one we're working on
        // plus the replacement item.
        let results = [...old.results.filter((oldItem: Tag) => oldItem.id !== data.id), data];
        results = results.sort((a, b) => {
          return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
        });
        return {
          ...old,
          results,
        };
      });
    },
  });

  // Modal methods
  const [show, setShow] = useState(false);
  const [modalTag, setModalTag] = useState('');

  const validateTagDoesNotExist = async (tagName: string) => {
    if (!tagName) {
      return false;
    }
    const tags = await checktagByNameAndId(tagName, modalTag.id);
    console.log(`Got ${tags.count} tags when checking for duplicates`);
    return tags.count == 0;
  };

  const handleClose = () => {
    // Clear the inputs, hide the modal
    setShow(false);
  };

  const handleShow = (tag, e) => {
    // Get the item, populate the inputs, show the modal
    console.log(`Modal is opening; tag ID is: ${tag.id}`);
    setModalTag(tag);
    setShow(true);
  };

  // Form methods
  const { register, handleSubmit, watch, errors } = useForm<Inputs>();
  const onSubmit = (data) => {
    console.log(`Data in submitted form is`, data);
    updateTag(data);
    handleClose();
  };

  return (
    <>
      <h1>
        <i className="fa fa-tags gray" />
        &nbsp;{isPageOwner ? 'Your tags' : 'Public tags for ' + userName}
      </h1>
      <div className="table-responsive">
        {isLoading ? (
          <div>Loading...</div>
        ) : isError ? (
          <div>Error: {error.message}</div>
        ) : (
          // `resolvedData` will either resolve to the latest page's data
          // or if fetching a new page, the last successful page's data
          <TagListInner
            data={resolvedData.results}
            userName={userName}
            isPageOwner={isPageOwner}
            onEditTagClick={handleShow}
          />
        )}
      </div>

      {/*Pagination*/}
      {page === 1 && latestData && !latestData.next ? null : (
        <div className="well v-offset-above-3 hidden-print">
          <div className="row">
            <div className="col-xs-2 col-sm-3">
              {page > 1 ? (
                <div className="text-left">
                  <a onClick={() => setPage((old) => Math.max(old - 1, 0))} className="btn btn-default" rel="prev">
                    <i className="fa fa-caret-left no-underline" />
                    &nbsp;
                    <span className="hidden-xs hidden-sm">Previous</span>
                    <span className="hidden-xs hidden-md hidden-lg">Prev.</span>
                  </a>
                </div>
              ) : null}
            </div>
            <div className="col-xs-8 col-sm-6">
              <div className="text-center large">
                <span className="hidden-xs">
                  {isFetching ? (
                    <>
                      <i className="fa fa-spinner fa-pulse gray" />
                      &nbsp;Loading...
                    </>
                  ) : (
                    'Page ' + page
                  )}
                </span>
              </div>
            </div>
            <div className="col-xs-2 col-sm-3">
              {latestData && latestData.next ? (
                <div className="text-right">
                  <a
                    onClick={() =>
                      // Here, we use `latestData` so the Next Page
                      // button isn't relying on potentially old data
                      setPage((old) => (!latestData || !latestData.next ? old : old + 1))
                    }
                    rel="next"
                    className="btn btn-default"
                  >
                    <span className="hidden-xs">Next</span>&nbsp;
                    <i className="fa fa-caret-right no-underline" />
                  </a>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      <Modal show={show} onHide={handleClose} animation={false}>
        <Modal.Header closeButton>
          <Modal.Title componentClass="h2">Edit Tag</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {!modalTag ? (
            <>
              <i className="fa fa-spinner fa-pulse gray" />
              &nbsp;Loading...
            </>
          ) : (
            <>
              <form className="form-horizontal" onSubmit={handleSubmit(onSubmit)}>
                <input type="hidden" value={modalTag.id} name="id" ref={register} />
                <div className={!errors.name ? 'form-group' : 'form-group has-error'}>
                  <label htmlFor="name" className="col-sm-2 control-label">
                    Tag Name
                  </label>
                  <div className="col-sm-10">
                    <input
                      type="text"
                      className="form-control"
                      name="name"
                      placeholder="A name for your tag..."
                      defaultValue={modalTag ? modalTag.name : ''}
                      ref={register({
                        required: true,
                        pattern: /^[a-z0-9-]*$/,
                        validate: validateTagDoesNotExist,
                      })}
                    />
                    <p className="gray">
                      <i className="fa fa-info-circle" /> Note that changing the tag name changes its link, and your
                      bookmarks or browser history may fail.
                    </p>
                    {errors.name?.type === 'required' && (
                      <p className="has-error help-block">This field is required.</p>
                    )}
                    {errors.name?.type === 'pattern' && (
                      <p className="has-error help-block">Only lowercase letters, numbers, and '-' are allowed.</p>
                    )}
                    {errors.name?.type === 'validate' && (
                      <p className="has-error help-block">You already have a tag with that name.</p>
                    )}
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="title" className="col-sm-2 control-label">
                    Title
                  </label>
                  <div className="col-sm-10">
                    <input
                      type="text"
                      className="form-control"
                      name="title"
                      placeholder="A brief, one-line summary of your tag..."
                      defaultValue={modalTag ? modalTag.title : ''}
                      ref={register}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="description" className="col-sm-2 control-label">
                    Description
                  </label>
                  <div className="col-sm-10">
                    <p className="gray">
                      Provide any additional comments you have about this tag, describing the kinds of dockets it
                      contains or why you created it.
                    </p>
                    <textarea
                      className="form-control"
                      name="description"
                      placeholder="A long description of your tag..."
                      rows="6"
                      defaultValue={modalTag ? modalTag.description : ''}
                      ref={register}
                    />
                    <p className="text-right">
                      <a href="/help/markdown/">Markdown Supported</a>
                    </p>
                  </div>
                </div>

                <div className="form-group">
                  <div className="col-sm-offset-2 col-sm-10">
                    <div className="checkbox">
                      <label>
                        <input type="checkbox" ref={register} name="published" defaultChecked={modalTag.published} />{' '}
                        Published
                      </label>
                    </div>
                  </div>
                </div>
              </form>
            </>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button onClick={handleSubmit(onSubmit)} bsStyle="primary" bsSize="large">
            Save Changes
          </Button>
        </Modal.Footer>
      </Modal>
    </>
  );
};

export default TagList;
