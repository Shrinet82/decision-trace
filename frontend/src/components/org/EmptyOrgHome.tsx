import React from 'react';
import { FileUp, GitBranch, PenLine } from 'lucide-react';
import { PageFrame } from '../PageFrame';
import { useIngest } from '../ingest/ingestContext';
import { FEATURES } from '../../config/features';

const big =
  'flex flex-1 flex-col items-start gap-2 rounded-panel border border-border bg-surface p-4 text-left transition-colors hover:bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent';

/** Home for an organization whose graph has nothing in it yet. */
export const EmptyOrgHome: React.FC<{ orgName: string }> = ({ orgName }) => {
  const ingest = useIngest();
  return (
    <PageFrame header={<h1 className="m-0 text-sm font-medium text-text">{orgName}</h1>}>
      <div className="mx-auto flex max-w-[720px] flex-col gap-6 px-5 py-12 min-[900px]:px-10">
        <div className="flex flex-col gap-2">
          <h2 className="m-0 text-xl font-semibold">This brain is empty. Add your first sources.</h2>
          <p className="m-0 max-w-prose text-text-2">
            Decision Trace reads meeting notes, tickets and ADRs, works out which decisions were made, by whom
            and on what evidence, and keeps them in a graph you can ask questions of.
          </p>
        </div>
        <div className="flex flex-col gap-3 min-[600px]:flex-row">
          {FEATURES.upload && (
            <button type="button" className={big} onClick={() => ingest?.openDrawer('files')}>
              <FileUp size={18} aria-hidden="true" className="text-accent" />
              <span className="text-base font-semibold">Upload files</span>
              <span className="text-sm text-muted">Markdown, text or PDF: up to 10 files, 1 MB each.</span>
            </button>
          )}
          {FEATURES.github && (
            <button type="button" className={big} onClick={() => ingest?.openDrawer('github')}>
              <GitBranch size={18} aria-hidden="true" className="text-accent" />
              <span className="text-base font-semibold">Import from GitHub</span>
              <span className="text-sm text-muted">A public repository&rsquo;s ADRs, decision PRs and issues.</span>
            </button>
          )}
          <button type="button" className={big} onClick={() => ingest?.openDrawer('paste')}>
            <PenLine size={18} aria-hidden="true" className="text-accent" />
            <span className="text-base font-semibold">Paste text</span>
            <span className="text-sm text-muted">Meeting notes, a ticket or an announcement.</span>
          </button>
        </div>
      </div>
    </PageFrame>
  );
};
