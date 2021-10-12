import React from 'react';
import { appFetch } from './_fetch';
import { Table } from 'react-bootstrap';
import './disclosure-page.css';
import { useParams } from 'react-router-dom';
import { disclosureModel } from './_disclosure_models';
import { convertTD } from './_disclosure_helpers';
import debounce from 'lodash.debounce';

interface TableNavigationInnerProps {
  disclosures: string;
}

interface Person {
  id: number;
  name_first: string;
  name_last: string;
  slug: string;
}

interface Row {
  id: number;
  filepath: string;
  person: Person;
  year: string;
  thumbnail: string;
  page_number: number;
  redacted: boolean;
}

interface Data {
  has_been_extracted: boolean;
  addendum_content_raw: string;
  filepath: string;
  thumbnail: string;
  id: number;
}

const TableNavigation: React.FC<TableNavigationInnerProps> = (disclosures) => {
  return <React.Fragment>{MainSection(disclosures)}</React.Fragment>;
};

function isDescendant(parent: HTMLElement, child: HTMLElement) {
  let node = child.parentNode;
  while (node != null) {
    if (node == parent) {
      return true;
    }
    node = node.parentNode;
  }
  return false;
}

const MainSection = (disclosures) => {
  const years = disclosures['years'].split(',');
  console.log(years)
  const doc_ids = disclosures['ids'].split(',');
  const { disclosure_id } = useParams();
  const { judge_id } = useParams();
  const [data, setData] = React.useState('');
  const [judge, setJudge] = React.useState([]);
  const judge_name = disclosures['judge'];
  const is_admin = disclosures['admin'] == 'True';
  const indx = doc_ids.indexOf(disclosure_id);
  const [visible, setVisible] = React.useState(false);

  const handleClickOutside = (event: Event) => {
    const query_container = document.getElementById('sidebar-query-box');
    if (!isDescendant(query_container, event.target)) {
      setVisible(false);
    }
    if (query_container == event.target) {
      setVisible(true);
    }
  };

  const handleEsc = (event: { keyCode: number }) => {
    if (event.keyCode === 27) {
      setVisible(false);
    }
  };

  React.useEffect(() => {
    document.addEventListener('click', handleClickOutside, true);
    window.addEventListener('keydown', handleEsc);
  }, []);

  const fetchDisclosure = async (doc_id: number) => {
    try {
      const response = await appFetch(`/api/rest/v3/financial-disclosures/?person=${judge_id}&id=${doc_id}`);
      console.log(response);
      setData(response['results'][0]);
    } catch (error) {
      console.log(error);
    }
  };

  if (data == '') {
    fetchDisclosure(disclosure_id);
  }

  const fetchJudge = async (query: string) => {
    try {
      const response: any = await appFetch(`/api/rest/v3/disclosure-typeahead/?fullname=${query}&order_by=name_last`);
      setJudge(response['results']);
    } catch (error) {
      setJudge([]);
    }
  };

  const changeHandler = (event: string) => {
    if (event.length < 2) {
      setVisible(false)
    } else {
      fetchJudge(event);
      setVisible(true)
    }
  };

  const debounceFetchJudge = React.useMemo(() => debounce(changeHandler, 300), []);
  const urlList = window.location.pathname.split('/');
  const judgeUrl = [urlList[0], urlList[1], urlList[2], urlList[5], urlList[6]].join('/');
  return (
    <div>
      {data != '' && data.has_been_extracted ? (
        <div>
          <div className={'v-offset-below-3 v-offset-above-3'}>
            <div className={'col-md-9'}>
              {Tabs(data, years, years[indx], fetchDisclosure, doc_ids, judge_name, judgeUrl)}
              <div className="tabcontent">
                {TableMaker(data, 'investments', is_admin)}
                {TableMaker(data, 'gifts', is_admin)}
                {TableMaker(data, 'reimbursements', is_admin)}
                {TableMaker(data, 'spouse_incomes', is_admin)}
                {TableMaker(data, 'debts', is_admin)}
                {TableMaker(data, 'non_investment_incomes', is_admin)}
                {TableMaker(data, 'agreements', is_admin)}
                {TableMaker(data, 'positions', is_admin)}
                {data.addendum_content_raw != '' ? (
                  <>
                    <h3>Addendum</h3>
                    <article>{data.addendum_content_raw}</article>{' '}
                  </>
                ) : (
                  ''
                )}
              </div>
            </div>
            <div className={'col-md-3'}>{Sidebar(data, is_admin, judge, debounceFetchJudge, visible)}</div>
          </div>
        </div>
      ) : data != '' && data.has_been_extracted == false ? (
        <div>
          <div className={'v-offset-below-3 v-offset-above-3'}>
            <div className={'col-sm-9'}>
              {Tabs(data, years, years[indx], fetchDisclosure, doc_ids, judge_name, judgeUrl)}
              <div className="tabcontent">
                <div className={'text-center v-offset-above-4'}>
                  <i className="fa fa-exclamation-triangle gray" />
                  <h1>Table extraction failed.</h1>
                  <p>
                    <a href={data.filepath}>Click here to view the disclsoure as a PDF document</a>
                  </p>
                </div>
              </div>
            </div>
            <div className={'col-sm-3'}>{Sidebar(data, is_admin, judge, debounceFetchJudge, visible, setVisible)}</div>
          </div>
        </div>
      ) : (
        <h1 className={'text-center'}>Loading...</h1>
      )}
    </div>
  );
};

const TableMaker = (data: Data, key: string, is_admin: boolean) => {
  const url = data.filepath;
  const disclosure_id = data.id;
  const rows = data[key];
  const fields = disclosureModel[key]['fields'];
  const title: string = disclosureModel[key]['title'];
  let api_key = key.replaceAll('_', '-');
  if (api_key == 'positions') {
    api_key = `disclosure-${api_key}`;
  }

  return (
    <div>
      {rows.length > 0 ? (
        <div className="table-responsive">
          <h3>
            {title}
            <a href={`/api/rest/v3/${api_key}/?financial_disclosure__id=${disclosure_id}`}>
              <i className="fa fa-code gray pull-right" />
            </a>
          </h3>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th key={''}> </th>
                {is_admin ? <th>Admin</th> : ''}
                {Object.entries(fields).map(([key, value]) => {
                  return <th key={value}>{key}</th>;
                })}
              </tr>
            </thead>
            <tbody>
              {rows
                .sort((x: Data, y: Data) => {
                  return x.id > y.id ? 1 : -1;
                })
                .map((entry: Row) => {
                  return (
                    <tr key={entry.id} className={''}>
                      <td>
                        <a title={'Go to PDF'} href={url + '#page=' + entry.page_number}>
                          <i className="fa fa-file-text-o gray" />
                        </a>
                        &nbsp;
                        {entry.redacted ? (
                          <i title={'Redaction present in row'} className="fa fa-file-excel-o black" />
                        ) : (
                          ''
                        )}
                      </td>
                      {is_admin ? (
                        <td>
                          <a href={`/admin/disclosures/${key.replaceAll('_', '').slice(0, -1)}/${entry.id}/`}>
                            <i className="fa fa-pencil gray" />
                          </a>
                        </td>
                      ) : (
                        ''
                      )}

                      {Object.entries(fields).map(([key, value]) => {
                        return (
                          <td key={key}>
                            {convertTD(entry[value], title, value)}
                            {entry[value] == -1 ? <i className="fa fa-eye-slash black" /> : ''}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
            </tbody>
          </Table>
        </div>
      ) : (
        ''
      )}
    </div>
  );
};

const Support = () => {
  return (
    <div id={'support'}>
      <h3>
        <span>
          Support FLP <i className="fa fa-heart-o red pull-right" />
        </span>
      </h3>
      <p className="v-offset-above-1">
        CourtListener is a project of{' '}
        <a href="https://free.law" target="_blank" rel="noreferrer">
          Free Law Project
        </a>
        , a federally-recognized 501(c)(3) non-profit. We rely on donations for our financial security.
      </p>
      <p>Please support our work with a donation.</p>
      <p>
        <a href="" className="btn btn-danger btn-lg btn-block">
          Donate Now
        </a>
      </p>
    </div>
  );
};

const Thumb = (data: Data) => {
  return (
    <div className="v-offset-below-4">
      <h3>
        <span>
          Download
          <a href={`/api/rest/v3/financial-disclosures/?id=${data.id}`}>
            <i className="fa fa-code gray pull-right" />
          </a>
        </span>
      </h3>
      <hr />
      <a href={data.filepath}>
        <img
          src={data.thumbnail}
          alt="Thumbnail of first page of disclosure"
          className="img-responsive thumbnail shadow img-thumbnail judge-pic"
          width={'100%'}
        />
      </a>
    </div>
  );
};

const Sidebar = (
  data: Data,
  is_admin: boolean,
  judge: Row[],
  fetchJudge: React.ChangeEventHandler<HTMLInputElement> | undefined,
  visible,
) => {
  return (
    <div>
      {is_admin ? AdminPanel(data) : ''}
      {data.thumbnail ? Thumb(data) : ''}
      {Notes()}
      {SearchPanel(judge, fetchJudge, visible)}
      {Support()}
    </div>
  );
};

const Notes = () => {
  return (
    <div className={'v-offset-below-4'}>
      <h3>
        <span>
          Notes <i className="fa fa-sticky-note-o pull-right" />
        </span>
      </h3>
      <hr />
      <span>The data in this file was extracted with OCR technology and may contain typos.</span>
      <ul className={'v-offset-above-2 v-offset-below-2'}>
        <li>
          <i className="fa fa-file-text-o gray" /> Links to the PDF row (if possible).
        </li>
        <li>
          <i className="fa fa-file-excel-o black" /> The row may contain a redaction.
        </li>
        <li>
          <i className="fa fa-eye-slash black" /> Indicates failed extraction in the cell.
        </li>
      </ul>
      <span>
        You can read more about financial disclosures at the{' '}
        <a href={'https://www.uscourts.gov/sites/default/files/guide-vol02d.pdf'}>
          Guide to Judiciary Policy on Ethics and Judicial Conduct
        </a>
        .
      </span>
    </div>
  );
};

const SearchPanel = (
  judge: Row[],
  fetchJudge: React.ChangeEventHandler<HTMLInputElement> | undefined,
  visible: boolean
) => {
  function update({ ...data }) {
    const query: string = data.target.value;
    fetchJudge(query);
  }

  const onFocusClick = (url: string) => {
    if (event.button == 2) {
      event.preventDefault();
    }
    if (event.button == 0 || event.keyCode == 13) {
      event.preventDefault();
      window.location = url;
    }
  };

  const onReturn = () => {
    console.log(judge.length)
    console.log(event.keyCode)
    if (judge.length == 1 && event.keyCode == 13) {
      onFocusClick(judge[0].latest_disclosure_url);
    }
  };

  return (
    <div className={'v-offset-below-4 table-parent'}>
      <h3>
        <span>
          Search <i className="fa fa-search gray pull-right" />
        </span>
      </h3>
      <hr />
      <input
        id={'sidebar-query-box'}
        onChange={update}
        autoComplete={'off'}
        autoCorrect={'off'}
        autoCapitalize={'off'}
        spellCheck={'false'}
        className={'form-control input-sm'}
        onKeyDown={onReturn}
        placeholder={'Search for judges by name…'}
        tabIndex={300}
      />
      <table className={visible ? 'search-panel-table' : 'hide-table'}>
        <tbody className={'cursor'}>
          {judge.map((row: Row) => {
            return (
              <tr
                className={'tr-results cursor'}
                key={row.id}
                onKeyDown={() => onFocusClick(row.latest_disclosure_url)}
                onMouseDown={() => onFocusClick(row.latest_disclosure_url)}
                tabIndex={301}
              >
                <td className={'col-lg-9 col-md-9 col-sm-11 col-xs-10'}>
                  <h4 className={'text-left'}>{row.name_full}</h4>
                  <p className={'text-left'}>{row.position_str}</p>
                </td>
                <td className={'col-lg-3 col-md-3 col-sm-1 col-xs-2 '}>
                  {row.thumbnail_path != null ? (
                    <img
                      src={row.thumbnail_path != null ? row.thumbnail_path : '/static/png/logo-initials-only.png'}
                      alt="Thumbnail of first page of disclosure"
                      height={'50'}
                      className="img-responsive thumbnail shadow img-thumbnail judge-pic"
                    />
                  ) : (
                    <div className={'img-responsive thumbnail shadow img-thumbnail judge-pic'}>
                      <i height={'150'} className={'fa fa-user fa-10x missing-judge'}></i>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const AdminPanel = (data: Data) => {
  return (
    <div className={'v-offset-below-4'}>
      <h3>
        <span>
          Admin <i className="fa fa-key red pull-right" />
        </span>
      </h3>
      <hr />
      <a href={`/admin/disclosures/financialdisclosure/${data.id}/`}>Disclosure Admin Page</a>
    </div>
  );
};

const Tabs = (
  data: Data,
  years: [string],
  year: string,
  fetchDisclosure,
  doc_ids: [number],
  judge_name: string,
  judgeUrl: string
) => {
  const pathname = window.location.pathname;
  const slug = pathname.split('/')[5];
  console.log(years, "YEARS")
  return (
    <div>
      <h1 className="text-center">
        Financial Disclosures for J.&nbsp;
        <a href={judgeUrl}>{judge_name}</a>
      </h1>
      <ul className="nav nav-tabs v-offset-below-2 v-offset-above-3" role="">
        {years.map((yr, index) => {
          return (
            <li key={`${yr}_${index}`} className={year == yr ? 'active' : ''} role="presentation">
              <a
                href={`../../${doc_ids[index]}/${slug}/`}
                onClick={() => {
                  fetchDisclosure(yr, index);
                }}
              >
                <i className="fa fa-file-text-o gray" />
                &nbsp; {yr}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default TableNavigation;
