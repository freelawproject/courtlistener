import React from 'react';

const Modal: React.FC = () => {
  return (
    <div className="modal hidden-print" role="dialog" id="modal-edit-delete">
      <div className="modal-dialog modal-sm" role="document">
        <div className="modal-content"></div>
      </div>
    </div>
  );
};

export default Modal;
