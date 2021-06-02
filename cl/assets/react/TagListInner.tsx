import React, { useState } from 'react';
import { Tag } from './_types';
import format from 'date-fns/format';
import parseISO from 'date-fns/parseISO';
import Button from 'react-bootstrap/lib/Button';
import Switch from 'react-input-switch';
import { updateTags } from './_useTags';

interface TagListInnerProps {
  data: Tag[];
  userName: string;
  isPageOwner: boolean;
  onEditTagClick?: () => void;
}

type ToggleProps = {
  state: boolean;
  name: string;
  id: number;
};

const Toggle = ({ state, name, id }: ToggleProps) => {
  const { modifyTags, deleteTags } = updateTags();
  const [value, setValue] = useState(+state);
  function trigger_state_change(key: number) {
    setValue(key);
    modifyTags({ published: !!key, name: name, id: id } as Tag);
  }
  return <Switch className={'toggle'} value={value} onChange={trigger_state_change} />;
};

const TagListInner: React.FC<TagListInnerProps> = ({ data, isPageOwner, userName }) => {
  const { modifyTags, deleteTags } = updateTags();
  const [rows, setRows] = React.useState(data);

  const delete_tag = (e: any, tag_id: number) => {
    if (window.confirm('Are you sure you want to delete this item?')) {
      deleteTags(tag_id);
      const index = data.findIndex((x) => x.id === tag_id);
      data.splice(index, 1);
      setRows(data);
    }
  };

  const onRowClick = (e: any, name: string) => {
    if (e.metaKey || e.ctrlKey) {
      window.open(`/tags/${userName}/${name}/`);
    } else {
      window.location.href = `/tags/${userName}/${name}/`;
    }
  };

  return (
    <div className="table-responsive">
      <table className="table settings-table tablesorter-bootstrap">
        <thead>
          <tr>
            <th>Name</th>
            <th>Created</th>
            <th>Views</th>
            {isPageOwner && <th>Public</th>}
            {isPageOwner && <th>Delete</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((tag) => {
            return (
              <tr>
                <td style={{ cursor: 'pointer' }} onClick={(event) => onRowClick(event, tag.name)}>
                  <span className="tag">{tag.name}</span>
                </td>
                <td style={{ cursor: 'pointer' }} onClick={(event) => onRowClick(event, tag.name)}>
                  {format(parseISO(tag.date_created || ''), 'MMM d, yyyy')}
                </td>
                <td style={{ cursor: 'pointer' }} onClick={(event) => onRowClick(event, tag.name)}>
                  {tag.view_count}
                </td>
                {isPageOwner && (
                  <>
                    <td>
                      <Toggle id={tag.id} name={tag.name} state={tag.published} />
                    </td>
                    <td>
                      <Button
                        id={`dlt_${tag.id}`}
                        onClick={(event) => delete_tag(event, Number(`${tag.id}`))}
                        className={'fa fa-trash btn-sm inline delete-tag'}
                      >
                        {' '}
                        Delete
                      </Button>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default TagListInner;
