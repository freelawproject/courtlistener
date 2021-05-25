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

  function go_to(e: any) {
    window.location.href = `/tags/${user}/${name}/`;
    e.preventDefault();
    e.stopPropagation();
  }

  return (
    <a className="list-group-item cursor">
      {isCreateItem ? (
        <p>
          <strong>{name}</strong>
        </p>
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
            <i className="fa fa-external-link cursor" onClick={(e) => go_to(e)} title="View this tag" />
          </span>
        </div>
      )}
    </a>
  );
};
