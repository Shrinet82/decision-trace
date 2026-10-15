import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { AskPage } from './pages/AskPage';
import { EmptyRoutePage } from './pages/EmptyRoutePage';

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<AskPage />} />
        <Route
          path="decisions"
          element={
            <EmptyRoutePage
              title="Decisions"
              description="Audit lifecycle, health, and status across all engineering decisions."
            />
          }
        />
        <Route
          path="graph"
          element={
            <EmptyRoutePage
              title="Graph"
              description="Global interactive topology of the Company Brain knowledge graph."
            />
          }
        />
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
