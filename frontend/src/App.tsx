import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { OrgLayout } from './org/OrgLayout';
import { AgentsPage } from './pages/AgentsPage';
import { AskPage } from './pages/AskPage';
import { DecisionPage } from './pages/DecisionPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { GraphPage } from './pages/GraphPage';
import { HomePage } from './pages/HomePage';
import { LandingPage } from './pages/LandingPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PeoplePage } from './pages/PeoplePage';
import { PersonPage } from './pages/PersonPage';
import { SourcesPage } from './pages/SourcesPage';
import { SystemPage } from './pages/SystemPage';
import { SystemsPage } from './pages/SystemsPage';

/** The full map moved from /graph to /explore; keep old links (and their ?node=) working. */
const GraphRedirect: React.FC = () => {
  const { search } = useLocation();
  return <Navigate to={`/app/explore${search}`} replace />;
};

const LEGACY_SECTIONS = new Set(['ask', 'agents', 'decisions', 'systems', 'people', 'explore', 'sources']);

/** Before /app existed the app lived at the root: send /decisions/DEC-11 and friends to /app/…. */
const LegacyRedirect: React.FC = () => {
  const { pathname, search } = useLocation();
  const first = pathname.split('/').filter(Boolean)[0];
  if (first && LEGACY_SECTIONS.has(first)) return <Navigate to={`/app${pathname}${search}`} replace />;
  return <NotFoundPage standalone />;
};

const appRoutes = (
  <>
    <Route index element={<HomePage />} />
    <Route path="ask" element={<AskPage />} />
    <Route path="agents" element={<AgentsPage />} />
    <Route path="decisions" element={<DecisionsPage />} />
    <Route path="decisions/:code" element={<DecisionPage />} />
    <Route path="systems" element={<SystemsPage />} />
    <Route path="systems/:name" element={<SystemPage />} />
    <Route path="people" element={<PeoplePage />} />
    <Route path="people/:name" element={<PersonPage />} />
    <Route path="explore" element={<GraphPage />} />
    <Route path="graph" element={<GraphRedirect />} />
    <Route path="sources" element={<SourcesPage />} />
    <Route path="*" element={<NotFoundPage />} />
  </>
);

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app" element={<OrgLayout sample />}>
        {appRoutes}
      </Route>
      <Route path="/app/o/:org" element={<OrgLayout />}>
        {appRoutes}
      </Route>
      <Route path="*" element={<LegacyRedirect />} />
    </Routes>
  );
};
