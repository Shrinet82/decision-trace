import React from 'react';
import { Plus } from 'lucide-react';
import { useIngest } from './ingest/ingestContext';
import { btnOutline } from './ui';

/** Opens the global "Add source" drawer. Hidden outside the app shell (no ingest context). */
const AddSourceButton: React.FC = () => {
  const ingest = useIngest();
  if (!ingest) return null;
  return (
    <button type="button" className={btnOutline} aria-haspopup="dialog" onClick={ingest.openDrawer}>
      <Plus size={13} aria-hidden="true" />
      Add source
    </button>
  );
};

export interface PageFrameProps {
  /** Breadcrumb or tab strip shown at the left of the 44px top bar. */
  header: React.ReactNode;
  /** Small outline buttons shown at the right of the top bar. */
  actions?: React.ReactNode;
  /** Right properties / inspector panel. Stacks below the content on narrow screens. */
  panel?: React.ReactNode;
  children: React.ReactNode;
}

export const PageFrame: React.FC<PageFrameProps> = ({ header, actions, panel, children }) => {
  const ingest = useIngest();
  return (
    <main id="main-content" tabIndex={-1} className="flex min-w-0 flex-1 flex-col bg-surface">
      <header className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-b border-divider px-5 py-1">
        <div className="flex min-w-0 items-center gap-1.5 text-muted">{header}</div>
        {(actions || ingest) && (
          <div className="flex flex-wrap gap-1.5">
            {actions}
            <AddSourceButton />
          </div>
        )}
      </header>
      <div className="flex flex-1 flex-wrap">
        <div className="min-w-0 flex-[999_1_480px]">{children}</div>
        {panel}
      </div>
    </main>
  );
};

export interface SidePanelProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

/** Right-hand properties panel container shared by all three pages. */
export const SidePanel: React.FC<SidePanelProps> = ({ label, children, className = '' }) => (
  <aside
    aria-label={label}
    className={`flex min-w-0 flex-[1_1_260px] flex-col gap-4 border-l border-divider bg-panel p-5 max-[899px]:max-w-none max-[899px]:border-l-0 max-[899px]:border-t min-[900px]:max-w-[300px] ${className}`}
  >
    {children}
  </aside>
);

export const PropertyList: React.FC<{ children: React.ReactNode; labelWidth?: number }> = ({
  children,
  labelWidth = 96,
}) => (
  <dl
    className="m-0 grid items-center gap-y-3"
    style={{ gridTemplateColumns: `${labelWidth}px minmax(0, 1fr)` }}
  >
    {children}
  </dl>
);

export const Property: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <>
    <dt className="text-muted">{label}</dt>
    <dd className="m-0 flex min-w-0 items-center gap-1.5 break-words">{children}</dd>
  </>
);
