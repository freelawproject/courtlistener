import React from 'react';

interface ListItemProps {
  id: number | string;
  name: string;
  dockets?: number[];
  assocId?: number;
  isSelected: boolean;
  user: string | boolean | undefined;
}

export const ListItem: React.FC<ListItemProps> = ({ id, name, assocId, isSelected, user }) => {
  const isCreateItem = name.startsWith('Create Tag: ');

  return (
    <a className="list-group-item" style={isCreateItem ? { cursor: 'default' } : {}}>
      {isCreateItem ? (
        <p>{name}</p>
      ) : (
        <div className="form-check form-check-inline">
          <input
            type="checkbox"
            id={assocId?.toString()}
            value={name}
            checked={isSelected}
            onChange={(ev) => ev.preventDefault()}
            style={{ marginRight: '1rem' }}
            className={`form-check position-static ${isSelected ? 'checked' : ''}`}
            data-tagid={id}
          />
          <label className="form-check-label">{name}</label>
          <span className="float-right gray">
            <i
              className="fa fa-external-link cursor"
              onClick={() => (window.location.href = `/tags/${user}/${name}/`)}
              title="View this tag"
            />
          </span>
        </div>
      )}
    </a>
  );
};
