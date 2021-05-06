import React, { useState } from 'react';
import { Tag } from './_types';
import { format, parseISO } from 'date-fns';
import {Button} from "react-bootstrap";
import Switch from 'react-input-switch';
import {updateTags} from "./_useTags";


interface TagListInnerProps {
  data: Tag[];
  userName: string;
  isPageOwner: boolean;
  onEditTagClick?: () => void;
}

type ToggleProps = {
    state: boolean;
    name: string;
    id: number
}

const Toggle = ({state, name, id}: ToggleProps) => {
  const {modifyTags, deleteTags} = updateTags();
  const [value, setValue] = useState(+state);
  function trigger_state_change(key: number) {
    setValue(key)
    modifyTags({published: !!key, name: name, id: id} as Tag)
  }
  return <Switch className={'toggle'} value={value} onChange={trigger_state_change} />;
};

const TagListInner: React.FC<TagListInnerProps> = ({ data, isPageOwner, userName }) => {
  const {modifyTags, deleteTags} = updateTags();
  const delete_tag = (e: any, tag_id: number) => {
    if (window.confirm('Are you sure you wish to delete this item?')) {
      deleteTags(tag_id)
      window.location.reload(false)
    }
  }

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
          {data.map((tag) => {
            return (
              <tr>
                <td
                style={{"cursor": "pointer"}}
                onClick={() => (window.location.href = `/tags/${userName}/${tag.name}/`)}>
                  <a href={`/tags/${userName}/${tag.name}/`} className="black-link">
                    <span className="tag">{tag.name}</span>
                  </a>
                </td>
                <td style={{"cursor": "pointer"}}
                onClick={() => (window.location.href = `/tags/${userName}/${tag.name}/`)}
                  >{format(parseISO(tag.date_created || ""), 'MMM d, yyyy')}</td>
                <td
                style={{"cursor": "pointer"}}
                onClick={() => (window.location.href = `/tags/${userName}/${tag.name}/`)}
                >{tag.view_count}</td>
                {isPageOwner && (
                  <>
                    <td>
                      <Toggle id={tag.id} name={tag.name} state={tag.published}/>
                    </td>
                    <td >
                      <Button
                        id={`dlt_${tag.id}`}
                        onClick={event => delete_tag(event, Number(`${tag.id}`))}
                        className={"fa fa-trash btn-sm inline delete-tag"}> Delete</Button>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  )
};

export default TagListInner;
