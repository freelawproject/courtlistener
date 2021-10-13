import { GROSS_VALUE, INCOME_GAIN, VALUATION_METHODS } from './_disclosure_models';
import React from 'react';
import { DebouncedFunc } from 'lodash';

interface Row {
  id: number;
  oldest_disclosure_url: string;
  name_full: string;
  position_str: string;
  disclosure_years: string;
  thumbnail_path: string;
}

export function isDescendant(parent: HTMLElement | null, child: HTMLElement | null) {
  if (child == null) {
    return false;
  }

  let node = child.parentNode;
  while (node != null) {
    if (node == parent) {
      return true;
    }
    node = node.parentNode;
  }
  return false;
}

export const convertTD = (value: string | number, table: string, key: string) => {
  if (value == -1 || !value) {
    return '';
  }
  if (['Investments', 'Debts'].indexOf(table) == -1) {
    return value;
  }
  if (['transaction_value_code', 'value_code', 'gross_value_code'].indexOf(key) > -1) {
    return `${GROSS_VALUE[value]} (${value})`;
  }
  if (['income_during_reporting_period_code', 'transaction_gain_code'].indexOf(key) > -1) {
    return `${INCOME_GAIN[value]} (${value})`;
  }
  if (key == 'gross_value_method' && value) {
    return `${VALUATION_METHODS[value]} (${value})`;
  }
  return value;
};

const InstantSearchResults = (
  update: React.ChangeEventHandler<HTMLInputElement> | undefined,
  onReturn: (e: KeyboardEvent) => void,
  visible: boolean,
  data: Row[],
  onFocusClick: (event: React.MouseEvent<HTMLTableRowElement>, url: string) => void,
  onFocusKeyPress: (event: React.KeyboardEvent<HTMLTableRowElement>, url: string) => void,
  input_size: string
) => {
  return (
    <React.Fragment>
      <input
        className={input_size}
        name="disclosures-filter"
        id="id_disclosures_search"
        autoComplete={'off'}
        autoCorrect={'off'}
        autoCapitalize={'off'}
        spellCheck={'false'}
        onChange={update}
        onKeyDown={(e) => onReturn(e)}
        type="search"
        tabIndex={300}
        placeholder="Search for judges by name…"
      />
      <table className={visible ? 'table-instant-results' : 'hide'}>
        <tbody>
          {data.map((row: Row) => {
            return (
              <tr
                tabIndex={301}
                onKeyDown={(e) => onFocusKeyPress(e, row.oldest_disclosure_url)}
                onMouseDown={(e) => onFocusClick(e, row.oldest_disclosure_url)}
                key={row.id}
                className="tr-results cursor"
              >
                <td className="col-xs-10 col-sm-10 col-lg-10 table-data-name">
                  <h4 className={'text-left judge-name'}>{row.name_full}</h4>
                  <p className={'text-left gray'}>{row.position_str}</p>
                </td>
                <td className="col-xs-2 col-sm-2 col-lg-2 table-data-portrait">
                  {row.thumbnail_path != null ? (
                    <img
                      src={row.thumbnail_path}
                      alt="Thumbnail of first page of disclosure"
                      width={'100%'}
                      className="img-responsive thumbnail shadow img-thumbnail judge-pic"
                    />
                  ) : (
                    <div className={'img-responsive thumbnail shadow img-thumbnail judge-pic'}>
                      <i className={'fa fa-user fa-10x missing-judge'} />
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </React.Fragment>
  );
};

export const DisclosureSearch = (
  data: Row[],
  fetchData: DebouncedFunc<(query: string) => Promise<void>> | React.ChangeEventHandler<HTMLInputElement>,
  visible: boolean,
  setVisible: { (value: React.SetStateAction<boolean>): void; (arg0: boolean): void },
  small: boolean
) => {
  function update({ ...data }) {
    const query: string = data.target.value;
    if (query.length > 1) {
      fetchData(query);
      setVisible(true);
    } else {
      setVisible(false);
    }
  }
  const onFocusClick = (event: MouseEvent, url: string) => {
    if (event.button == 2) {
      event.preventDefault();
    }
    if (event.button == 0) {
      event.preventDefault();
      window.location.pathname = url;
    }
  };

  const onFocusKeyPress = (event: KeyboardEvent, url: string) => {
    if (event.keyCode == 13) {
      event.preventDefault();
      window.location.pathname = url;
    }
  };

  const onReturn = (e: KeyboardEvent) => {
    if (data.length == 1 && e.keyCode == 13) {
      const location: string = data[0].oldest_disclosure_url;
      onFocusKeyPress(e, location);
    }
  };

  return (
    <div>
      {small ? (
        <div className={'v-offset-below-4 table-parent'}>
          <h3>
            <span>
              Search <i className="fa fa-search gray pull-right" />
            </span>
          </h3>
          <hr />
          {InstantSearchResults(update, onReturn, visible, data, onFocusClick, onFocusKeyPress, 'form-control input-md')}
        </div>
      ) : (
        <div className="v-offset-above-2 row">
          <div className="hidden-xs col-sm-1 col-md-2 col-lg-3" />
          <div className="col-xs-12 col-sm-10 col-md-8 col-lg-6 text-center form-group" id="main-query-box">
            <label className="sr-only" htmlFor="id_disclosures_search">
              Filter disclosures…
            </label>
            {InstantSearchResults(update, onReturn, visible, data, onFocusClick, onFocusKeyPress, 'form-control input-lg')}
          </div>
        </div>
      )}
    </div>
  );
};
