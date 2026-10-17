import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { AgentsPage } from './pages/AgentsPage';
import { AskPage } from './pages/AskPage';
import { DecisionPage } from './pages/DecisionPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { GraphPage } from './pages/GraphPage';
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { PeoplePage } from './pages/PeoplePage';
import { PersonPage } from './pages/PersonPage';
import { SourcesPage } from './pages/SourcesPage';
import { SystemPage } from './pages/SystemPage';
import { SystemsPage } from './pages/SystemsPage';

/** The full map moved from /graph to /explore; keep old links (and their ?node=) working. */
const GraphRedirect: React.FC = () => {
  const { search } = useLocation();
  return <Navigate to={`/explore${search}`} replace />;
};

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
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
      </Route>
    </Routes>
  );
};
