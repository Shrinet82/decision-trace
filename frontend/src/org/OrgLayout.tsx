import React from 'react';
import { useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { OrgProvider } from './OrgContext';
import { setCurrentOrg } from './orgState';

/**
 * The app frame for one organization. `/app/*` is the sample organization (slug null);
 * `/app/o/:org/*` is a user organization. The slug is recorded before children render so API
 * helpers read the right one, and the shell remounts when the organization changes.
 */
export const OrgLayout: React.FC<{ sample?: boolean }> = ({ sample }) => {
  const { org } = useParams();
  const slug = sample ? null : (org ?? null);
  setCurrentOrg(slug);
  return (
    <OrgProvider slug={slug}>
      <AppShell key={slug ?? 'sample'} />
    </OrgProvider>
  );
};
