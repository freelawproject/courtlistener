import React from 'react';
import ReactDOM from 'react-dom';
import { BrowserRouter, Switch, Route } from 'react-router-dom';
import TagSelect from './TagSelect';
import TagList from './TagList';
import { TagMarkdown } from './TagPage';
import DisclosureList from "./DisclosureList";
import DisclosureViewer from "./DisclosureViewer";

const App = () => {
  const root = document.getElementById('react-root');
  const data = JSON.parse(JSON.stringify(root!.dataset));

  return (
    <BrowserRouter>
      <Switch>
        <Route path="/docket">
          <TagSelect {...data} />
        </Route>
        <Route exact path={`/tags/:userName/`}>
          <TagList userId={data.requestedUserId} userName={data.requestedUser} isPageOwner={data.isPageOwner} />
        </Route>
        <Route path={`/tags/:userName/:id`}>
          <TagMarkdown {...data} />
        </Route>
        <Route exact path={`/financial-disclosures/`}>
          <DisclosureList {...data} />
        </Route>
        <Route path={'/person/:judge_id/disclosure/:disclosure_id/:slug/'}>
          <DisclosureViewer {...data} />
        </Route>
      </Switch>
    </BrowserRouter>
  );
};

ReactDOM.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
  document.getElementById('react-root')
);
