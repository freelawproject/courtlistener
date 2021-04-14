import React from 'react';
import { useInfiniteQuery, useMutation, queryCache, useQuery } from 'react-query';
import { appFetch } from './_fetch';
import { ApiResult, Tag, Association } from './_types';

interface UseTagsProps {
  docket: number;
}

export const useTags = ({ docket }: UseTagsProps) => {
  const [textVal, setTextVal] = React.useState<string>('');

  const getTags = React.useCallback(
    async (key: string, page = 1) => await appFetch(`/api/rest/v3/tags/?page=${page}`),
    []
  );

  const getAssociations = React.useCallback(
    async (key: string) => await appFetch(`/api/rest/v3/docket-tags/?docket=${docket}`),
    [docket]
  );

  const postTag = React.useCallback(
    async ({ name }: { name: string }) =>
      await appFetch('/api/rest/v3/tags/', {
        method: 'POST',
        body: { name },
      }),
    []
  );

  const postAssoc = React.useCallback(
    async ({ tag }: { tag: number }) =>
      await appFetch('/api/rest/v3/docket-tags/', {
        method: 'POST',
        body: { tag, docket },
      }),
    [docket]
  );

  const deleteAssoc = React.useCallback(
    async ({ assocId }: { assocId: number }) =>
      await appFetch(`/api/rest/v3/docket-tags/${assocId}/`, {
        method: 'DELETE',
      }),
    []
  );

  const { data: assocData } = useQuery('associations', getAssociations);

  const associations = assocData ? (assocData as ApiResult<Association>).results : [];

  const {
    status,
    data: tags,
    isFetching,
    isFetchingMore,
    fetchMore,
    canFetchMore,
  } = useInfiniteQuery('tags', getTags, {
    // if the lastPage has a next key, extract the page number
    getFetchMore: (lastPage, allPages) => {
      const nextPage = (lastPage as ApiResult<Tag>).next;
      if (!nextPage) return false;
      const matches = nextPage.match(/page=(\d+)/);
      return matches && matches[1] ? matches[1] : false;
    },
  });

  const [deleteAssociation] = useMutation(deleteAssoc, {
    onSuccess: (data, variables) => {
      // update the cache to remove the just-deleted association
      queryCache.setQueryData('associations', (old: any) => ({
        ...old,
        results: old.results.filter((assoc: Association) => assoc.id !== variables.assocId),
      }));
    },
  });

  const [addNewAssociation] = useMutation(postAssoc, {
    onSuccess: (data, variables) =>
      // update the cache to add the just created association
      queryCache.setQueryData('associations', (old: any) => ({
        ...old,
        results: [...old.results, data],
      })),
  });

  const [addNewTag] = useMutation(postTag, {
    // if the new tag is created, update the cache to include the just-created tag
    // then fire the addNewAssociation mutation
    onSuccess: (data, variables) => {
      setTextVal('');
      queryCache.setQueryData('tags', (old: any) => {
        const keys = Object.keys(old);
        const lastKey = keys[keys.length - 1];
        const lastResult = old[lastKey];
        const newResult = {
          ...lastResult,
          results: [
            ...lastResult.results,
            { ...(data as Tag), dockets: [...(data as Tag).dockets, docket] },
          ],
        };
        return { ...old, [lastKey]: newResult };
      });
      addNewAssociation({ tag: (data as Tag).id });
    },
  });

  // memoize the tag entries to reduce renders and apply the filter
  const filteredTags = React.useMemo(() => {
    const flatTags = !tags
      ? []
      : Object.entries(tags)
          .map(([key, apiResult]) => (apiResult as ApiResult<Tag>).results)
          .flat(1);

    // rebuild tagData with the assocId
    const enhancedTags = flatTags.map((tag: Tag) => {
      if (!associations) return tag;
      const assoc = (associations as Association[]).find((a) => a.tag === tag.id);
      return { ...tag, assocId: assoc?.id };
    });

    // case insensitive alpha sorting
    const sortedTags = enhancedTags.sort((a, b) => {
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });

    if (!textVal) return sortedTags;

    let exactMatch;

    const filtered: Tag[] | undefined = sortedTags.filter((tag: Tag) => {
      if (!!textVal && tag.name === textVal) {
        exactMatch = true;
      }
      return tag.name.toLowerCase().includes(textVal.toLowerCase());
    });

    if (exactMatch) {
      return filtered;
    } else {
      // inject a create option to precede the listed tags
      return [
        {
          id: '-10',
          name: `Create Option: ${textVal}`,
          dockets: [],
        },
        ...filtered,
      ];
    }
  }, [tags, textVal, associations]);

  return {
    infiniteQueryState: {
      status,
      canFetchMore,
      isFetching,
      isFetchingMore,
      fetchMore,
    },
    tags: filteredTags,
    textVal,
    setTextVal,
    associations,
    addNewTag,
    addNewAssociation,
    deleteAssociation,
  };
};
