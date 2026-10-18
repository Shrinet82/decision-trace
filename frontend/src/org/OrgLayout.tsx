import React, { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useOrgInfo } from '../api/hooks';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { OrgProvider } from './OrgContext';
import { forgetOrg, rememberOrg } from './orgStore';
import { setCurrentOrg } from './orgState';
import { btnOutline } from '../components/ui';

const OrgGone: React.FC<{ slug: string }> = ({ slug }) => {
  useDocumentTitle('Organization not found');
  useEffect(() => forgetOrg(slug), [slug]);
  return (
    <main id="main-content" className="flex min-h-screen items-center justify-center bg-bg p-4 text-text">
      <div role="status" className="flex max-w-prose flex-col items-start gap-2 rounded-panel border border-divider bg-subtle p-4">
        <h1 className="m-0 text-lg font-semibold">Organization not found</h1>
        <p className="m-0 text-muted">
          This organization does not exist. It may have been deleted, or removed after 72 hours without activity.
        </p>
        <Link to="/app" className={btnOutline}>
          Open the sample organization
        </Link>
      </div>
    </main>
  );
};

/**
 * The app frame for one organization. `/app/*` is the sample organization (slug null);
 * `/app/o/:org/*` is a user organization. The slug is recorded before children render so API
 * helpers read the right one, and the shell remounts when the organization changes.
 */
export const OrgLayout: React.FC<{ sample?: boolean }> = ({ sample }) => {
  const { org } = useParams();
  const slug = sample ? null : (org ?? null);
  setCurrentOrg(slug);
  const info = useOrgInfo(slug);
  useEffect(() => {
    if (info.data && !info.data.sample) rememberOrg(info.data);
  }, [info.data]);

  if (slug && info.error?.status === 404) return <OrgGone slug={slug} />;
  return (
    <OrgProvider slug={slug}>
      <AppShell key={slug ?? 'sample'} />
    </OrgProvider>
  );
};
