import React from 'react';

interface ListItemProps {
  id: number | string;
  name: string;
  dockets?: number[];
  assocId?: number;
  isSelected: boolean;
}

export const ListItem: React.FC<ListItemProps> = ({ id, name, assocId, isSelected }) => {
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
        </div>
      )}
    </a>
  );
};
