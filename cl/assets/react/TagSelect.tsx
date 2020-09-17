import React from 'react';
import { useVirtual } from 'react-virtual';
import { useCombobox } from 'downshift';
import { ListItem } from './ListItem';
import { useTags } from './_useTags';
import { Association, UserState } from './_types';

function getDataFromReactRoot() {
  const div = document.querySelector('div#react-root');
  if (div && div instanceof HTMLElement) {
    const authStr = div.dataset.authenticated;
    if (!authStr) return {};
    const strParts = authStr.split(':', 2);
    return {
      userId: parseInt(strParts[0], 10),
      userName: strParts[1],
      editUrl: div.dataset.editUrl,
    };
  } else {
    console.error('Unable to fetch credentials from server. Tags disabled.');
    return { userName: undefined, editUrl: undefined };
  }
}

function getDocketIdFromH1Tag() {
  const h1 = document.querySelector('h1[data-id]');
  if (h1 && h1 instanceof HTMLElement) {
    return parseInt(h1.dataset.id as string);
  } else {
    console.error('Unable to fetch docket number from page. Tags disabled.');
  }
}

const TagSelect: React.FC<UserState> = ({ userId, userName, editUrl }) => {
  const [validationError, setValidationError] = React.useState<null | string>(null);

  const docket = getDocketIdFromH1Tag();

  const {
    infiniteQueryState: { status, canFetchMore, isFetching, isFetchingMore, fetchMore },
    textVal,
    setTextVal,
    tags,
    associations,
    addNewTag,
    addNewAssociation,
    deleteAssociation,
  } = useTags({ docket: docket as number, enabled: !!docket && userName, userId: userId });

  const parentRef = React.useRef(null);
  const rowVirtualizer = useVirtual({
    size: canFetchMore ? tags.length + 1 : tags.length,
    parentRef,
    estimateSize: React.useCallback(() => 40, []),
  });

  // fetchmore if we are at the bottom of the list
  React.useEffect(() => {
    const [lastItem] = [...rowVirtualizer.virtualItems].reverse();

    if (!lastItem) return;

    if (lastItem.index === rowVirtualizer.virtualItems.length - 1 && canFetchMore && !isFetchingMore) {
      console.log('fetching more');
      fetchMore();
    }
  }, [canFetchMore, fetchMore, tags.length, isFetchingMore, rowVirtualizer.virtualItems]);

  const {
    isOpen,
    getToggleButtonProps,
    getLabelProps,
    getMenuProps,
    getInputProps,
    getComboboxProps,
    highlightedIndex,
    getItemProps,
  } = useCombobox({
    inputValue: textVal,
    itemToString: (item) => (item ? item.name : ''),
    // set to none to select multiple
    selectedItem: null,
    items: tags,
    scrollIntoView: () => {},
    stateReducer: (state, actionAndChanges) => {
      const { changes, type } = actionAndChanges;
      switch (type) {
        case useCombobox.stateChangeTypes.InputKeyDownEnter:
        case useCombobox.stateChangeTypes.ItemClick:
          return {
            ...changes,
            isOpen: true, // keep menu open after selection.
            highlightedIndex: state.highlightedIndex,
            inputValue: '',
          };
        default:
          return changes;
      }
    },
    onSelectedItemChange: ({ selectedItem }) => {
      if (!selectedItem) return;
      const isCreateItemOption = selectedItem.name.startsWith('Create Tag:');
      if (isCreateItemOption) {
        const validInput = textVal.match(/^[a-z0-9-]*$/);
        if (!validInput) {
          return setValidationError("Only lowercase letters, numbers, and '-' allowed");
        }
        return addNewTag({ name: selectedItem.name.replace('Create Tag: ', '') });
      }
      const isAlreadySelected = !associations
        ? false
        : !!(associations as Association[]).find((a) => a.tag === selectedItem.id);

      if (isAlreadySelected) {
        console.log(`Removing ${selectedItem.name} from tags for docket ${docket}`);
        deleteAssociation({ assocId: (selectedItem as any).assocId });
      } else {
        console.log(`Adding ${selectedItem.name} to tags for docket ${docket}`);
        addNewAssociation({ tag: parseInt(selectedItem.id as string, 10) });
      }
    },
    onHighlightedIndexChange: ({ highlightedIndex }) => {
      if (highlightedIndex && highlightedIndex >= 0) {
        rowVirtualizer.scrollToIndex(highlightedIndex);
      }
    },
  });

  // manually type nativeEvent as any
  // https://github.com/downshift-js/downshift/issues/734
  const disableDownshiftMenuToggle = ({ nativeEvent }: { nativeEvent: any }) =>
    (nativeEvent.preventDownshiftDefault = true);

  return (
    <div>
      <button
        {...getToggleButtonProps({
          onClick: (event) => {
            // Anonymous user
            if (!userName) {
              disableDownshiftMenuToggle(event);
            }
          },
          onKeyDown: (event) => {
            if (!userName) {
              disableDownshiftMenuToggle(event);
            }
          },
        })}
        aria-label="toggle tag menu"
        className={!userName ? 'btn btn-success logged-out-modal-trigger' : 'btn btn-success'}
      >
        <i className="fa fa-tags" />
        &nbsp;Tags <span className="caret" />
      </button>

      <div
        className="list-group"
        style={{
          marginTop: '2px',
          border: isOpen ? '1px solid grey' : 'none',
          zIndex: isOpen ? 10 : 0,
          minWidth: '300px',
          maxWidth: '500px',
          position: 'absolute',
        }}
      >
        <a
          type="button"
          className="list-group-item"
          style={{ display: isOpen ? 'block' : 'none' }}
          {...getLabelProps()}
        >
          Apply tags to this item
        </a>
        <a
          type="button"
          style={{ padding: '1em', display: isOpen ? 'block' : 'none' }}
          {...getComboboxProps()}
          className="list-group-item"
        >
          <input
            {...getInputProps({
              onBlur: (e: React.FocusEvent) => setValidationError(null),
              onChange: (e: React.ChangeEvent<HTMLInputElement>) => setTextVal(e.target.value),
            })}
            className={`form-control ${validationError && 'is-invalid'}`}
            placeholder="Search tags…"
          />
          {validationError && (
            <div style={{ padding: '1px' }} className="invalid-feedback">
              {validationError}
            </div>
          )}
        </a>
        <div
          style={{
            overflowY: isOpen ? 'auto' : 'hidden',
            maxHeight: '500px',
          }}
        >
          <div
            {...getMenuProps({ ref: parentRef })}
            style={{
              height: `${rowVirtualizer.totalSize}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {isOpen &&
              rowVirtualizer.virtualItems.map((virtualRow, index) => {
                const isLoaderRow = virtualRow.index > tags.length - 1;
                const tag = tags[virtualRow.index];
                return (
                  <div
                    key={virtualRow.index}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  >
                    <div
                      key={tag ? tag.name : 'loading row'}
                      {...getItemProps({ item: tag, index: virtualRow.index })}
                      style={{
                        backgroundColor: highlightedIndex === virtualRow.index ? '#bde4ff' : '',
                      }}
                    >
                      {isLoaderRow ? (
                        canFetchMore ? (
                          'Loading more...'
                        ) : (
                          'Nothing more to load'
                        )
                      ) : (
                        <ListItem
                          isSelected={!!associations.find((a) => a.tag === tag.id)}
                          key={virtualRow.index}
                          user={userName}
                          {...tag}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
        <a style={{ display: isOpen ? 'block' : 'none' }} className="list-group-item" href={editUrl}>
          <i className="fa fa-pencil" style={{ marginRight: '1em' }} />
          Edit Tags
        </a>
      </div>
    </div>
  );
};

export default TagSelect;
