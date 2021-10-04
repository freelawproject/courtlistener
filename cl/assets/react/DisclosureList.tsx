import React from 'react';
import { appFetch } from './_fetch';
import { UserState } from './_types';


const scrollToRef = (ref) => {
  window.scrollTo(0, ref.current.offsetTop)
}

const DisclosureList: React.FC<UserState> = () => {
  const [data, setData] = React.useState<any>([]);
  const [query, setQuery] = React.useState("");
  const myRef = React.useRef(null)
  const executeScroll = () => scrollToRef(myRef)

  const fetchData = async (query: string) => {
    try {
      const response = await appFetch(`/api/rest/v3/financial-disclosures/?person__fullname=${query}`)
      setQuery(query)
      setData(response['results']);

      console.log(response['results'])

    } catch (error) {
      console.log(error);
    }
  };

  function update({ ...data }) {
    var query = data.target.value
    fetchData(query)
  }

  return (
    <div>
      {DisclosureHeader(executeScroll)}
      {DisclosureSearch(data, query, update)}
      {DisclosureFooter(myRef)}
    </div>
  )
};

const DisclosureHeader = (executeScroll) => {
  return (
    <div>
      <h1 className="text-center">Judicial Financial Disclosures Database</h1>
      <p className="text-center gray large">A collaboration of
        <a href="https://demandprogress.org">&#32;Demand Progress</a>,
        <a href="https://fixthecourt.com">&#32;Fix the Court</a>,
        <a href="https://free.law">&#32;Free Law Project</a>, and
        <a href="https://muckrock.com">&#32;MuckRock</a>.
      </p>
      <p className="text-center"><a onClick={executeScroll} className="btn btn-default">Learn More</a></p>
    </div>
  )
}

const DisclosureSearch = (data, query, update) => {
  return (
    <div>
      <div className="row v-offset-above-2">
        <div className="hidden-xs col-sm-1 col-md-2 col-lg-3"></div>
        <div className="col-xs-12 col-sm-10 col-md-8 col-lg-6 text-center form-group" id="main-query-box">
          <label className="sr-only" htmlFor="id_disclosures_filter">Filter disclosures…</label>
          <input className="form-control input-lg"
                 name="disclosures-filter"
                 id="id_disclosures_filter"
                 autoComplete="off"
                 onChange={update}
                 type="text"
                 placeholder="Filter disclosures by typing a judge's name here…"/>
            <div>
              <table className={"table-instant-results"}>
              {query != "" ? (
                <tbody>
                    {data.map((row) => {
                      return (
                        <tr className="col-xs-7 col-md-8 col-lg-12 tr-results">
                          <td className="col-md-9">
                            <a href={`/financial-disclosures/${row.person.id}/${row.person.slug}/?id=${row.id}`}>
                              <h4 className={"text-left"}>Judge {row.person.name_first} {row.person.name_last}</h4>
                            </a>
                            <p className={"text-left"}>{row.year}</p>
                          </td>
                          <td className="col-md-3">
                              <a href={ row.filepath }>
                                <img src={ row.thumbnail }
                                     alt="Thumbnail of disclosure form"
                                     width={"100"}
                                     height={"150"}
                                     className="img-responsive thumbnail shadow img-thumbnail"
                                />
                              </a>
                            </td>
                        </tr>
                      );
                    })}
                </tbody>
              ) : (
                <tbody></tbody>
              )
              }
      </table>
      </div>
        </div>
      </div>
    </div>
  )
}

const DisclosureFooter = (myRef) => {
  return (
    <div className="row v-offset-above-4 abcd" ref={myRef}>
      <div className="col-xs-12 col-sm-6">
        <p className="lead">Yadda Yadda Yadda</p>
        <p> Honestly this is where I think we could explain about collaborators?</p>
        <p>Our financial disclosure database is a collection of over 250,000 pages
          of financial records drawn from over 26,000 tiff and PDF files.
          We requested these files from the federal judiciary beginning in 2017
          and have been gathering them since that time.</p>

      </div>
      <div className="col-xs-12 col-sm-6">
        <p className="lead">The Data</p>
        <p>Financial Disclosures by federal judges is mandated by law. Starting int 1974 Judges
        have been required to make thier financial records available for 6 years. Beginning in 2017
        we began requesting the financial records of every federal judge. </p>
        <p>To learn more about how you can use API endpoints click this link.</p>
        <p><a href={"https://www.courtlistener.com/api/rest-info/#financialdisclosure-endpoint"}>https://www.courtlistener.com/api/rest-info/#financialdisclosure-endpoint</a></p>
      </div>
    </div>
  )
}

export default DisclosureList;
