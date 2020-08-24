import React from 'react';
import { useVirtual } from 'react-virtual';
import { useCombobox } from 'downshift';
import { ListItem } from './ListItem';
import { useTags } from './_useTags';
import { Association } from './_types';

const isAuthenticated = true;
function getDocketIdFromH1Tag() {
  // const h1 = document.querySelector("h1[data-id]");
  // return parseInt(h1.dataset.id);
  return 18; // mock 18 in dev
}

const TagSelect: React.FC = () => {
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
  } = useTags({ docket });

  const parentRef = React.useRef();
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
          };
        default:
          return changes;
      }
    },
    onSelectedItemChange: ({ selectedItem }) => {
      if (!selectedItem) return;
      const isCreateItemOption = selectedItem.name.startsWith('Create Option:');
      if (isCreateItemOption) {
        const validInput = textVal.match(/^[a-z-]*$/);
        if (!validInput) {
          return setValidationError("Only lowercase letters and '-' allowed");
        }
        return addNewTag({ name: selectedItem.name.replace('Create Option: ', '') });
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
    onInputValueChange: ({ inputValue }) => {
      if (inputValue) {
        setTextVal(inputValue);
      }
    },
  });

  return (
    <div style={{ padding: '2rem' }}>
      <button
        {...getToggleButtonProps()}
        disabled={!isAuthenticated}
        aria-label="toggle tag menu"
        className="btn btn-primary"
      >
        Tags <span className="caret"></span>
      </button>
      <div
        style={{
          marginTop: '2px',
          border: isOpen ? '1px solid grey' : 'none',
          maxWidth: '300px',
        }}
      >
        <li className="list-group-item" style={{ display: isOpen ? 'block' : 'none' }} {...getLabelProps()}>
          Apply tags to this item
        </li>
        <li
          style={{ padding: '1em', display: isOpen ? 'block' : 'none' }}
          {...getComboboxProps()}
          className="list-group-item list-group-item-action"
        >
          <input
            {...getInputProps({ onBlur: (e: React.FocusEvent) => setValidationError(null) })}
            className={`form-control ${validationError && 'is-invalid'}`}
            placeholder="Search for a tag"
          />
          {validationError && <div className="invalid-feedback">{validationError}</div>}
        </li>
        <div
          style={{
            overflowY: isOpen ? 'scroll' : 'hidden',
            maxHeight: '500px',
          }}
        >
          <div
            //@ts-ignore
            {...getMenuProps({ ref: parentRef })}
            style={{
              height: `${rowVirtualizer.totalSize}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {isOpen &&
              rowVirtualizer.virtualItems.map((virtualRow) => {
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
                      style={highlightedIndex === virtualRow.index ? { backgroundColor: '#bde4ff' } : {}}
                      key={tag ? tag.name : 'loading row'}
                      {...getItemProps({ item: tag, index: virtualRow.index })}
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
                          {...tag}
                        />
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
        <li style={{ display: isOpen ? 'block' : 'none' }} className="list-group-item list-group-item-action">
          <a className="btn btn-default" href="/edit-tags-url">
            <i className="fa fa-pencil mr-2" />
            Edit Labels
          </a>
        </li>
      </div>
    </div>
  );
};

export default TagSelect;
