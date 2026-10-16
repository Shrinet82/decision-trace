import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { AskPage } from './pages/AskPage';
import { DecisionsPage } from './pages/DecisionsPage';
import { GraphPage } from './pages/GraphPage';
import { EmptyRoutePage } from './pages/EmptyRoutePage';

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<AskPage />} />
        <Route path="decisions" element={<DecisionsPage />} />
        <Route path="graph" element={<GraphPage />} />
        <Route
          path="sources"
          element={
            <EmptyRoutePage
              title="Sources"
              description="Index of tickets, architecture records, and meeting minutes."
            />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
};
