import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { PageFrame } from '../components/PageFrame';
import { btnOutline } from '../components/ui';

/** Any address the app does not have a page for. */
export const NotFoundPage: React.FC = () => {
  const { pathname } = useLocation();
  return (
    <PageFrame header={<span className="text-sm font-medium text-text">Page not found</span>}>
      <div role="status" className="m-5 flex max-w-prose flex-col items-start gap-2 rounded-panel border border-divider bg-subtle p-4">
        <h1 className="m-0 text-lg font-semibold">Page not found</h1>
        <p className="m-0 text-muted">There is nothing at {pathname}. It may have moved, or the link may be mistyped.</p>
        <div className="flex flex-wrap gap-2">
          <Link to="/" className={btnOutline}>
            Go to Home
          </Link>
          <Link to="/decisions" className={btnOutline}>
            Browse decisions
          </Link>
        </div>
      </div>
    </PageFrame>
  );
};
