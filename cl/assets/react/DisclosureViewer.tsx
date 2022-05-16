import React from 'react';
import { Table } from 'react-bootstrap';
import './disclosure-page.css';
import { useParams } from 'react-router-dom';
import { disclosureModel } from './_disclosure_models';
import { convertTD, DisclosureSearch, fetchDisclosure } from './_disclosure_helpers';

interface DisclosureParams {
  disclosures: string;
  years: string;
  admin: string;
  ids: string;
  judge: string;
}

interface Row {
  id: number;
  newest_disclosure_url: string;
  name_full: string;
  position_str: string;
  disclosure_years: string;
  thumbnail_path: string;
}

interface Data {
  has_been_extracted: boolean;
  addendum_content_raw: string;
  filepath: string;
  thumbnail: string;
  id: number;
}

interface IDs {
  judge_id: string;
  disclosure_id: string;
  slug: string;
}

const TableNavigation: React.FC<DisclosureParams> = (disclosures) => {
  const empty_dict: Data = { addendum_content_raw: '', filepath: '', has_been_extracted: false, thumbnail: '', id: 0 };
  const [data, setData] = React.useState(empty_dict);
  const is_admin = disclosures['admin'] == 'True';

  return (
    <React.Fragment>
      <div>
        <div className={'v-offset-below-3 v-offset-above-3'}>
          {MainSection(disclosures, is_admin, data, setData)}
          {<div className={'col-md-3'}>{Sidebar(is_admin, data.id, data.thumbnail, data.filepath)}</div>}
        </div>
      </div>
    </React.Fragment>
  );
};

const MainSection = (
  disclosures: DisclosureParams,
  is_admin: boolean,
  data: Data,
  setData: React.Dispatch<React.SetStateAction<Data>>
) => {
  const years = disclosures['years'].split(',');
  const doc_ids = disclosures['ids'].split(',');
  const judge_name = disclosures['judge'];
  const parameters: IDs = useParams();
  const disclosure_id: string = parameters['disclosure_id'];
  const index = doc_ids.indexOf(disclosure_id);

  if (data.id == 0) {
    fetchDisclosure(setData, parameters);
  }

  return (
    <div>
      {data.has_been_extracted ? (
        <div>
          <div className={'col-md-9'}>
            {Tabs(data, years, years[index], fetchDisclosure, doc_ids, judge_name, parameters)}
            <div className="tabcontent">
              {TableMaker(data, 'agreements', is_admin)}
              {TableMaker(data, 'positions', is_admin)}
              {TableMaker(data, 'reimbursements', is_admin)}
              {TableMaker(data, 'non_investment_incomes', is_admin)}
              {TableMaker(data, 'spouse_incomes', is_admin)}
              {TableMaker(data, 'gifts', is_admin)}
              {TableMaker(data, 'debts', is_admin)}
              {TableMaker(data, 'investments', is_admin)}
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
        </div>
      ) : data.id != 0 && !data.has_been_extracted ? (
        <div>
          <div className={'col-sm-9'}>
            {Tabs(data, years, years[index], fetchDisclosure, doc_ids, judge_name, parameters)}
            <div className="tabcontent">
              <div className={'text-center v-offset-above-4 disclosure-page'}>
                <i className="fa fa-exclamation-triangle gray" />
                <h1>Table extraction failed.</h1>
                <p>
                  <a href={data.filepath}>Click here to view the disclosure as a PDF document</a>
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className={'col-md-9'}>
          <div id={'loader'}>
            <h1>Loading Disclosure</h1>
            <i className="fa fa-spinner fa-spin fa-3x fa-fw"></i>
          </div>
        </div>
      )}
    </div>
  );
};

const TableMaker = (data: Data, key: string, is_admin: boolean) => {
  const url = data.filepath;
  const disclosure_id = data.id;
  const rows = data[key];
  const fields: string[] = disclosureModel[key]['fields'];
  const title: string = disclosureModel[key]['title'];
  const api_key: string = disclosureModel[key]['api'];
  const admin_key: string = disclosureModel[key]['admin_key'];
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
                        {title == 'Investments' ? (
                          <a title={'Go to PDF'} href={url + '#page=' + entry.page_number}>
                            <i className="fa fa-file-text-o gray" />
                          </a>
                        ) : (
                          ''
                        )}
                        &nbsp;
                        {entry.redacted ? (
                          <i title={'Redaction present in row'} className="fa fa-file-excel-o black" />
                        ) : (
                          ''
                        )}
                      </td>
                      {is_admin ? (
                        <td>
                          <a href={`/admin/disclosures/${admin_key}/${entry.id}/`}>
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

const Thumb = (id: number, thumbnail: string, filepath: string) => {
  return (
    <div className="v-offset-below-4">
      <h3>
        <span>
          Download
          <a href={`/api/rest/v3/financial-disclosures/${id}/`}>
            <i className="fa fa-code gray pull-right" />
          </a>
        </span>
      </h3>
      <hr />
      <a href={filepath}>
        <img
          src={thumbnail}
          alt="Future Judicial Portrait"
          className="img-responsive thumbnail shadow img-thumbnail judge-pic"
          width={'100%'}
        />
      </a>
    </div>
  );
};

const Sidebar = (is_admin: boolean, id: number, thumbnail: string, filepath: string) => {
  return (
    <div>
      {is_admin ? AdminPanel(id) : ''}
      {thumbnail ? Thumb(id, thumbnail, filepath) : ''}
      {Notes()}
      {DisclosureSearch(true)}
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
      <p>
        You can read more about financial disclosures at the{' '}
        <a href={'https://www.uscourts.gov/sites/default/files/guide-vol02d.pdf'}>
          Guide to Judiciary Policy on Ethics and Judicial Conduct
        </a>
        , or the official{' '}
        <a href="https://free.law/pdf/disclosure-filing-instructions-2021.pdf">
          Filing Instructions for Judicial Officers and Employees
        </a>
        .
      </p>

      <p>
        Please report any security or privacy concerns to{' '}
        <span>
          <a href="mailto:&#115;&#101;&#099;&#117;&#114;&#105;&#116;&#121;&#064;&#102;&#114;&#101;&#101;&#046;&#108;&#097;&#119;">
            &#115;&#101;&#099;&#117;&#114;&#105;&#116;&#121;&#064;&#102;&#114;&#101;&#101;&#046;&#108;&#097;&#119;
          </a>
          .
        </span>
      </p>
    </div>
  );
};

const AdminPanel = (id: number) => {
  return (
    <div className={'v-offset-below-4'}>
      <h3>
        <span>
          Admin <i className="fa fa-key red pull-right" />
        </span>
      </h3>
      <hr />
      <a href={`/admin/disclosures/financialdisclosure/${id}/`}>Disclosure Admin Page</a>
    </div>
  );
};

const Tabs = (
  data: Data,
  years: string[],
  active_year: string,
  fetchDisclosure: (setData: any, parameters: any) => Promise<void>,
  doc_ids: string[],
  judge_name: string,
  parameters: IDs
) => {
  return (
    <div>
      <h1 className="text-center">
        Financial Disclosures for J.&nbsp;
        <a href={`/person/${parameters['judge_id']}/${parameters['slug']}/`}>{judge_name}</a>
      </h1>
      <ul className="nav nav-tabs v-offset-below-2 v-offset-above-3" role="">
        {years.map((year, index) => {
          return (
            <li key={`${year}_${index}`} className={active_year == year ? 'active' : ''} role="presentation">
              <a
                href={`../../${doc_ids[index]}/${parameters['slug']}/`}
                onClick={() => {
                  fetchDisclosure(year, index);
                }}
              >
                <i className="fa fa-file-text-o gray" />
                &nbsp; {year}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default TableNavigation;
