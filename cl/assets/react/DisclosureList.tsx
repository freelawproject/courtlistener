import React from 'react';
import { UserState } from './_types';
import { DisclosureSearch } from './_disclosure_helpers';

const DisclosureList: React.FC<UserState> = () => {
  return (
    <div>
      {DisclosureHeader()}
      {DisclosureSearch(false)}
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
          consider becoming a member.
        </p>
        <p>
          <a href="https://donate.free.law/forms/supportflp" className="btn btn-danger btn-lg">
            Join Now
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
