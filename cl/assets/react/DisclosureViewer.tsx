import React from "react";
import {appFetch} from "./_fetch";
import {Table} from "react-bootstrap";
import './disclosure-page.css';
import {useParams} from "react-router-dom";
import {disclosureModel, GROSS_VALUE, INCOME_GAIN, VALUATION_METHODS} from "./_disclosure_models";

interface TableNavigationInnerProps {
  disclosures: String;
}

const getIndex = (value, arr) => {
    for(var i = 0; i < arr.length; i++) {
        if(arr[i] === value.toString()) {
            return i;
        }
    }
    return 0
}


const TableNavigation: React.FC<TableNavigationInnerProps> = (disclosures) => {

  return (
    <React.Fragment>
      {MainSection(disclosures)}
    </React.Fragment>
  )
}

const MainSection = (disclosures) => {
  const years = disclosures['years'].split(",")
  const doc_ids = disclosures['ids'].split(",")
  const is_admin =  disclosures['admin'] == "True" ? true : false
  const judge_name = disclosures['judge']

  const [data, setData] = React.useState("");
  const [judge, setJudge] = React.useState([]);

  let { judge_id } = useParams();
  const search = window.location.search;
  const params = new URLSearchParams(search);
  var optional_doc_id = params.get('id');

  var start;
  var index;

  if (optional_doc_id == null ) {
    start = years[0]
    index = 0
  } else {
    index = getIndex(optional_doc_id, doc_ids)
    start = years[index]
  }
  const [year, setYear] = React.useState(start);
  const [id, setId] = React.useState(index);


  const fetchDisclosure = async (year: string, index: Number) => {
    try {
      const doc_id = doc_ids[index]
      const response = await appFetch(`/api/rest/v3/financial-disclosures/?person=${judge_id}&id=${doc_id}`)
      setData(response['results'][0]);
      setYear(year)
    } catch (error) {
      console.log(error);
    }
  };

   const fetchJudge = async (query: string) => {
      if (query == "") {
        setJudge([]);
      }
      else {
        try {
          const response = await appFetch(`/api/rest/v3/financial-disclosures/?person__fullname=${query}`)
          // console.log("resp", response['results'])
          setJudge(response['results']);
        } catch (error) {
          setJudge([]);
        }
      }
    };

  if (data == '') {
    fetchDisclosure(year, id)
  }

  return (
    <div>
      { data != "" && data.has_been_extracted == true ? (
          <div>
            <div className={"v-offset-below-3 v-offset-above-3"}>
              <div className={"col-lg-9"}>
                {Tabs(data, years, year, fetchDisclosure, doc_ids, judge_name)}
                <div className="tabcontent">
                    {TableMaker(data, "investments", is_admin)}
                    {TableMaker(data, "gifts", is_admin)}
                    {TableMaker(data, "reimbursements", is_admin)}
                    {TableMaker(data, "spouse_incomes", is_admin)}
                    {TableMaker(data, "debts", is_admin)}
                    {TableMaker(data, "non_investment_incomes", is_admin)}
                    {TableMaker(data, "agreements", is_admin)}
                    {TableMaker(data, "positions", is_admin)}

                    {data.addendum_content_raw != "" ? (<>
                      <h3>Addendum</h3>
                      <article>{data.addendum_content_raw}</article> </>) : ("")
                    }

                </div>
              </div>
              <div className={"col-lg-3"}>
                  {Sidebar(data, is_admin, judge, fetchJudge)}
              </div>

            </div>
          </div>
      ) : data.has_been_extracted == false ? (

        <div>
          <div className={"v-offset-below-3 v-offset-above-3"}>
            <div className={"col-lg-9"}>
              {Tabs(data, years, year, fetchDisclosure, doc_ids, judge_name)}
              <div className="tabcontent">
                <div className={"text-center v-offset-above-4"}>
                  <i className="fa fa-exclamation-triangle gray"></i>
                  <h1>Table extraction failed.</h1>
                  <p>You can still view this Financial Disclosure by clicking the thumbnail.</p>
                </div>
              </div>
            </div>
            <div className={"col-lg-3"}>
              {Sidebar(data, is_admin, judge, fetchJudge)}
            </div>
          </div>
        </div>
      ) : (<div className={"row"}><h3 className={"text-center"}> Loading ...</h3></div>)}
    </div>
  )
};

const convertTD = (value, table, key) => {
  if (value == -1) {
    return "[Failed OCR]"
  }

  if (table == "Investments" && key == "transaction_value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Debts" && key == "value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Investments" && key == "income_during_reporting_period_code" && value) {
    return `${INCOME_GAIN[value]} (${value})`
  }
  if (table == "Investments" && key == "gross_value_method" && value) {
    return `${VALUATION_METHODS[value]} (${value})`
  }
  if (table == "Investments" && key == "gross_value_code" && value) {
    return `${GROSS_VALUE[value]} (${value})`
  }
  if (table == "Investments" && key == "transaction_gain_code" && value) {
    return `${INCOME_GAIN[value]} (${value})`
  }

  return value
}

const TableMaker = (data, key, is_admin) => {

  const url = data.filepath
  const disclosure_id = data.id
  const rows = data[key]
  const fields = disclosureModel[key]['fields']
  const title = disclosureModel[key]['title']

  return (
    <div>
      {rows.length > 0 ? (
       <div className="table-responsive">
         <h3>{title}<a href={`/api/rest/v3/${key.replaceAll("_","-")}/?financial_disclosure__id=${disclosure_id}`}> <i className="fa fa-code gray pull-right"></i></a></h3>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th key={""}> </th>
                {is_admin == true ? (<th>Admin</th>) : ("")}
                {Object.entries(fields).map(([key, value]) => {
                  return (
                    <th key={value}>{key}</th>
                    )
                  })
                }
              </tr>
            </thead>
            <tbody>
              {rows.sort((x, y) => { return x.id > y.id ? 1 : -1; }).map((entry) => {
                return (
                  <tr key={entry.id} className={""}>
                    <td>
                      <a href={url + "#page=" + entry.page_number}>
                        <i className="fa fa-file-text-o gray"></i>
                      </a>
                      {entry.redacted == true ? (<i className="fa fa-file-excel-o black"></i>): ("")}
                    </td>
                    {is_admin == true ? (<td><a href={`/admin/disclosures/${key.replaceAll("_","").slice(0, -1)}/${entry.id}/`}><i className="fa fa-pencil gray"></i></a></td>) : ("")}

                    {Object.entries(fields).map(([key, value]) => {
                      return (
                        <td>{convertTD(entry[value], title, value)}</td>
                        )
                      })
                    }
                  </tr>
                )
                })
              }
            </tbody>
          </Table>
        </div>
        ) : ("")
      }
    </div>
  )
}

const Support = () => {
  return (
    <div id={"support"}>
    <h3><span>Support FLP <i className="fa fa-heart-o red"></i></span></h3>
      <p className="v-offset-above-1">
        CourtListener is a project of <a
        href="https://free.law" target="_blank">Free
        Law Project</a>, a federally-recognized 501(c)(3) non-profit. We
        rely on donations for our financial security.
      </p>
      <p>Please support our work with a donation.</p>
      <p>
        <a href=""
           className="btn btn-danger btn-lg btn-block">Donate Now</a>
      </p>
    </div>
  )
}

const Thumb = (data) => {
  return (
    <div className="v-offset-below-4">
      <h3><span>Download <i className="fa fa-download gray"></i></span></h3>
      <hr/>
        <a href={data.filepath }>
          <img src={data.thumbnail }
               alt="Thumbnail of disclosure form"
               width={"200"}
               className="img-responsive thumbnail shadow img-thumbnail img-rounded"
          ></img>
        </a>
    </div>
  )
}


const Sidebar = (data, is_admin, judge, fetchJudge) => {
  return (
    <div>
      {is_admin == true ? AdminPanel(data): ""}
      {Thumb(data)}
      {Notes()}
      {SearchPanel(judge, fetchJudge)}
      {Support()}
    </div>
  )
}

const Notes = () => {
  return (
    <div className={"v-offset-below-2"}>
      <h3><span>Notes <i className="fa fa-sticky-note-o"></i></span></h3>
      <hr/>
      <span>This disclosure was generated and text extracted by OCR.</span><br/><br/>
      <span>For more information about individual fields ... go here...</span><br/><br/>
      <span>The ⬛ icon indicates a redaction in the table row may exist.</span>
      <br/><br/><br/><br/>
    </div>
  )
}

const SearchPanel = (judge, fetchJudge) => {

  function update({ ...data }) {
    var query = data.target.value
    fetchJudge(query)
  }

  return (
    <div className={"v-offset-below-4 "}>
      <h3><span>Search <i className="fa fa-search gray"></i></span></h3>
      <hr/>
      <input onChange={update} className={"form-control input-sm"} placeholder={"Filter disclosures by typing a judge's name here…"}></input><br/>
      <table className="search-panel-table">
        <tbody>
        {judge.map((row) => {
            return (
                <tr key={row.id}>
                  <td className={"search-panel-td"}>
                    <a href={`/person/${row.person.id}/${row.person.slug}/financial-disclosures/?id=${row.id}`}>
                          <h4 className={"text-left"}>Judge {row.person.name_first} {row.person.name_last}</h4>
                        </a>
                    <p className={"text-left"}>{row.year}</p>
                  </td>
                </tr>
              )
            })
          }
        </tbody>
      </table>
    </div>
  )
}

const AdminPanel = (data) => {

  return (
    <div className={"v-offset-below-4"}>
      <h3><span>Admin <i className="fa fa-key red"></i></span></h3>
      <hr/>
      <span>If Admin provide special links to things</span>
      <a href={`/admin/disclosures/financialdisclosure/${data.id}/`}>Admin Page</a>
    </div>
  )
}

const Tabs = (data, years, year, fetchDisclosure, doc_ids, judge_name) => {
  return (
    <div>
      <h1 className="text-center">Financial Disclosures for J.&nbsp;
        <a href={".."}>{judge_name}</a> </h1>
        <ul className="nav nav-tabs v-offset-below-2 v-offset-above-3" role="">
          {years.map((yr, index) => {
                return (
                  <li className={(year == yr) ? "active" : ""}
                      role="presentation">
                    <a href={`?id=${doc_ids[index]}`} onClick={() => { fetchDisclosure(yr, index)}}>
                     <i className="fa fa-file-text-o gray"></i>&nbsp; {yr}
                    </a>
                  </li>
                )
              }
            )
          }
        </ul>
      </div>
  )
};

export default TableNavigation;
