import React from 'react';

interface ListItemProps {
  id: number | string;
  name: string;
  dockets?: number[];
  assocId?: number;
  isSelected: boolean;
}

export const ListItem: React.FC<ListItemProps> = ({ id, name, assocId, isSelected }) => {
  const isCreateItem = name.startsWith('Create Option: ');

  return (
    <li
      style={isCreateItem ? { cursor: 'default' } : {}}
      className="list-group-item list-group-item-action"
    >
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
            className={`form-check position-static ${isSelected ? 'checked' : ''}`}
            data-tagid={id}
          />
          <label className="ml-4 form-check-label">{name}</label>
        </div>
      )}
    </li>
  );
};
