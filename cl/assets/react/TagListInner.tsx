import React from 'react';
import { Tag } from './_types';
import { format, parseISO } from 'date-fns';

interface TagListInnerProps {
  data: Tag[];
  userName: string;
  isPageOwner: boolean;
}

const TagListInner: React.FC<TagListInnerProps> = ({ data, isPageOwner, userName }) => {
  return (
    <div className="table-responsive">
      <table className="table settings-table tablesorter-bootstrap">
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Created</th>
            <th>Views</th>
            {isPageOwner && <th colSpan={2}>Published</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((tag) => {
            return (
              <tr>
                <td>
                  <a href={`/api/rest/v3/tags/${userName}/${tag.name}`} className="black-link">
                    <span className="tag">{tag.name}</span>
                  </a>
                </td>
                <td>{tag.title || '(none)'}</td>
                <td>{format(parseISO(tag.date_created) || new Date(), 'MMM d, yyyy')}</td>
                <td>{tag.view_count}</td>
                {isPageOwner && (
                  <>
                    <td>{tag.published ? 'Yes' : 'No'}</td>
                    <td className="text-right">
                      <a href="" className="btn btn-primary btn-sm inline">
                        <i className="fa fa-pencil"></i>&nbsp;Edit
                      </a>
                      &nbsp;
                      <a title="Delete Tag" className="btn btn-danger btn-sm inline delete-tag-button" data-id={tag.id}>
                        <i className="fa fa-times"></i> Delete
                      </a>
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
