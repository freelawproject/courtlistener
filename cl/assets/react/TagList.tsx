import React from 'react';
import { useQuery } from 'react-query';
import TagListInner from './TagListInner';
import { appFetch } from './_fetch';
import { Tag, UserState } from './_types';

const TagList: React.FC<UserState> = ({ userId, userName, isPageOwner }) => {
  const [page, setPage] = React.useState(1);

  const getTags = React.useCallback(
    async (key: string, page = 1) =>
      await appFetch(`/api/rest/v3/tags/?user=${userId}&page=${page}&page_size=10&order_by=name`),
    []
  );
  const {
    isLoading,
    isError,
    error,
    data,
    isFetching,
   } = useQuery(['tags', page], getTags, { keepPreviousData : true })
  const latestData = data

  if (latestData == undefined) {
    return <div>Loading...</div>;
  }

  return (
     <div>
       {isPageOwner ? (<h1>Your Tags</h1>) : (<h1>Tags for: {userName}</h1>)}
       {isLoading ? (
         <div>Loading...</div>
       ) : isFetching ? (
         <div>Loading...</div>
       ) : isError ? (
         <div>Error: {(error as any).message} </div>
       ) : (

         <TagListInner
            data={(latestData as any).results as Tag[]}
            isPageOwner={isPageOwner as boolean}
            userName={userName as string}
          />
       )}
    {page === 1 && latestData && !(latestData as any).next ? null : (
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
              {latestData && (latestData as any).next ? (
                <div className="text-right">
                  <a
                    onClick={() =>
                      // Here, we use `latestData` so the Next Page
                      // button isn't relying on potentially old data
                      setPage((old) => (!latestData || !(latestData as any).next ? old : old + 1))
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
      {isFetching ? <span> Fetching...</span> : null}{' '}
    </div>
  );
};

export default TagList;
