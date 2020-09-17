import React from 'react';
import { usePaginatedQuery } from 'react-query';
import { useTags } from './_useTags';
import TagListInner from './TagListInner';
import { appFetch } from './_fetch';
import { UserState } from './_types';
import { userInfo } from 'os';

const TagList: React.FC<UserState> = ({ userId, userName, isPageOwner }) => {
  const [page, setPage] = React.useState(1);

  const getTags = React.useCallback(
    async (key: string, page = 1) =>
      await appFetch(`/api/rest/v3/tags/?user=${userId}&page=${page}&page_size=50&order_by=name`),
    []
  );
  const { isLoading, isError, error, resolvedData, latestData, isFetching } = usePaginatedQuery(
    ['tags', page],
    getTags
  );

  return (
    <>
      <h1>
        {console.log(isPageOwner)}
        <i className="fa fa-tags gray"></i>&nbsp;{isPageOwner ? 'Your tags' : 'Public tags for ' + userName}
      </h1>
      <div className="table-responsive">
        {isLoading ? (
          <div>Loading...</div>
        ) : isError ? (
          <div>Error: {error.message}</div>
        ) : (
          // `resolvedData` will either resolve to the latest page's data
          // or if fetching a new page, the last successful page's data
          <TagListInner data={resolvedData.results} userName={userName} isPageOwner={isPageOwner} />
        )}
      </div>
      <span>Current Page: {page}</span>
      <button onClick={() => setPage((old) => Math.max(old - 1, 0))} disabled={page === 1}>
        Previous Page
      </button>{' '}
      <button
        onClick={() =>
          // Here, we use `latestData` so the Next Page
          // button isn't relying on potentially old data
          setPage((old) => (!latestData || !latestData.next ? old : old + 1))
        }
        disabled={!latestData || !latestData.next}
      >
        Next Page
      </button>
      {
        // Since the last page's data potentially sticks around between page requests,
        // we can use `isFetching` to show a background loading
        // indicator since our `status === 'loading'` state won't be triggered
        isFetching ? <span> Loading...</span> : null
      }{' '}
    </>
  );
};

export default TagList;
