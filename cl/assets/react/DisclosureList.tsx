import React from 'react';
import { appFetch } from './_fetch';
import { UserState } from './_types';
import debounce from 'lodash.debounce';

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
}

const DisclosureList: React.FC<UserState> = () => {
  const [data, setData] = React.useState<Row[]>([]);
  const [query, setQuery] = React.useState('');

  React.useEffect(() => {
    const handleEsc = (event) => {
      if (event.keyCode === 27) {
        setQuery('');
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => {
      window.removeEventListener('keydown', handleEsc);
    };
  }, []);

  const fetchData = async (query: string) => {
    try {
      const response: any = await appFetch(`/api/rest/v3/disclosure-typeahead/?fullname=${query}`);
      const results: Row[] = response['results'];
      setQuery(query);
      setData(results);

      console.log(response['results']);
    } catch (error) {
      console.log(error);
    }
  };

  const changeHandler = (event: string) => {
    fetchData(event);
  };

  const debounceFetchJudge = React.useMemo(() => debounce(changeHandler, 300), []);

  return (
    <div>
      {DisclosureHeader()}
      {DisclosureSearch(data, query, debounceFetchJudge)}
      {DisclosureFooter()}
    </div>
  );
};

const DisclosureHeader = () => {
  return (
    <div>
      <h1 className="text-center">Judicial Financial Disclosures Database</h1>
      <p className="text-center gray large">
        Search and review the biggest database of judicial disclosures ever made.
      </p>
    </div>
  );
};

const DisclosureSearch = (
  data: Row[],
  query: string,
  fetchJudge: React.ChangeEventHandler<HTMLInputElement> | undefined
) => {
  function update({ ...data }) {
    const query: string = data.target.value;
    if (query.length > 1) {
      fetchJudge(query);
    }
  }

  return (
    <div>
      <div className="row v-offset-above-2">
        <div className="hidden-xs col-sm-1 col-md-2 col-lg-3" />
        <div className="col-xs-12 col-sm-10 col-md-8 col-lg-6 text-center form-group" id="main-query-box">
          <label className="sr-only" htmlFor="id_disclosures_filter">
            Filter disclosures…
          </label>
          <input
            className="form-control input-lg"
            name="disclosures-filter"
            id="id_disclosures_filter"
            autoComplete={'off'}
            autoCorrect={'off'}
            autoCapitalize={'off'}
            spellCheck={'false'}
            onChange={update}
            type="text"
            placeholder="Filter disclosures by typing a judge's name…"
          />
            <table className={'table-instant-results'}>
              {query != '' ? (
                <tbody>
                  {data.map((row: Row) => {
                    return (
                      <tr key={row.id} className="tr-results">
                        <a className={'table-row-link'} href={`${row.latest_disclosure_url}`}>
                          <td className="col-xs-8 col-sm-8 col-md-10 col-lg-10">
                            <h4 className={'text-left'}>{row.name_full}</h4>
                            <p className={'text-left'}>{row.position_str}</p>
                            <p className={'text-left'}>{row.disclosure_years}</p>
                          </td>

                          <td className="col-xs-4 col-sm-4 col-md-2 col-lg-2">
                            <img
                              src={row.thumbnail_path}
                              alt="Thumbnail of disclosure form"
                              height={'150'}
                              className="img-responsive thumbnail shadow img-thumbnail judge-pic"
                            />
                          </td>
                        </a>
                      </tr>
                    );
                  })}
                </tbody>
              ) : (
                <tbody />
              )}
            </table>
          </div>
        </div>
    </div>
  );
};

const DisclosureFooter = () => {
  return (
    <div className="row v-offset-above-4">
      <div className="col-md-4">
        <h3>About this Database</h3>
        <p>
          Every year, federal judges must complete lengthy documents listing any investments or other potential sources
          of conflict that they may have. By statute, these documents are available to the public for six years before
          they must be destroyed.
        </p>
        <p>
          In 2017, we began collecting these documents so they would not be thrown away. After extracting the data from
          the files we&apos;ve collected, we have build a first-of-its-kind database of over a million investment
          transactions, and more than 250,000 pages of judicial records.
        </p>
        <p>All of the information you find here is available via our APIs or by browsing our database of judges.</p>
        <p>
          Creating this database was an expensive project for our organization. If you find this work valuable, please
          consider making a donation
        </p>
        <p>
          <a href="/donate/?referrer=fds-homepage" className="btn btn-danger btn-lg">
            Donate Now
          </a>
        </p>
      </div>
      <div className="col-md-4">
        <h3>Coverage</h3>
        <p>This database is a collection of every disclosure we could find online or request under the law.</p>
        <p>To learn more about what we have found, please see our coverage page dedicated to the topic.</p>
        <p>
          If you know of sources of disclosures that we do not already have, please get in touch and we will be pleased
          to add it to our collection.
        </p>
        <p>
          <a href="/coverage/financial-disclosures/" className="btn btn-primary btn-lg">
            See Coverage
          </a>
        </p>
      </div>
      <div className="col-md-4">
        <h3>Learn More</h3>
        <ul>
          <li>
            <a href="https://free.law/2021/09/28/announcing-federal-financial-disclosures">
              Our blog post announcing the database
            </a>
          </li>
          <li>
            <a href="https://www.wsj.com/articles/131-federal-judges-broke-the-law-by-hearing-cases-where-they-had-a-financial-interest-11632834421?st=wm0bzo39zzjts1v">
              The Wall Street Journal&apos;s investigation using this data
            </a>
          </li>
          <li>
            <a href="https://www.uscourts.gov/sites/default/files/guide-vol02d.pdf">
              The official policies guiding financial disclosures
            </a>
          </li>
          <li>
            <a href="https://www.gao.gov/assets/gao-18-406.pdf">A GAO report on disclosures</a>
          </li>
          <li>
            <a href="https://www.govtrack.us/congress/bills/95/s555">
              The Ethics in Government Act establishing disclosure rules
            </a>
          </li>
          <li>
            <a href="https://web.archive.org/web/20190614103410/https://famguardian.org/PublishedAuthors/Media/KCStar/30da0058.404,.htm">
              Early investigative work on disclosures from 1998
            </a>
          </li>
        </ul>
      </div>
    </div>
  );
};

export default DisclosureList;
