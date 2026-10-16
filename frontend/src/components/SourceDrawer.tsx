import React from 'react';
import type { SourceRef } from '../api/types';
import { formatLongDate } from '../utils/format';
import { findQuote } from '../utils/highlight';
import { Drawer } from './Drawer';

const TYPE_LABEL: Record<string, string> = {
  ticket: 'Ticket',
  meeting: 'Meeting notes',
  document: 'Document',
};

/** The verbatim text of a decision's source, with the evidence quote highlighted. */
export const SourceDrawer: React.FC<{ source: SourceRef | null; onClose: () => void }> = ({
  source,
  onClose,
}) => {
  const text = source?.text ?? '';
  const match = source ? findQuote(text, source.quote) : null;

  return (
    <Drawer open={Boolean(source)} onClose={onClose} title="Source" titleId="source-drawer-title">
      {source && (
        <div className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-text">{source.id}</span>
            <span className="text-xs text-muted">
              {TYPE_LABEL[source.type] ?? source.type}
              {source.date && ` · ${formatLongDate(source.date) || source.date}`}
            </span>
            {source.title && source.title !== source.id && (
              <span className="text-text-2">{source.title}</span>
            )}
          </div>

          {source.quote && !match && (
            <div className="flex flex-col gap-1 rounded-panel bg-subtle px-3 py-2.5">
              <span className="text-xs text-muted">Evidence quote (not found verbatim in the text below)</span>
              <blockquote className="m-0 text-text-2">“{source.quote}”</blockquote>
            </div>
          )}

          <section aria-label="Source text" className="flex flex-col gap-1.5">
            <h3 className="m-0 text-xs font-medium text-muted">
              Text{match ? ' · evidence highlighted' : ''}
            </h3>
            <p
              data-testid="source-text"
              className="m-0 whitespace-pre-wrap break-words rounded-panel border border-divider px-3 py-2.5 leading-[1.6] text-text-2"
            >
              {match ? (
                <>
                  {match.before}
                  <mark className="rounded-[3px] bg-[#FCEFC7] px-0.5 text-text">{match.match}</mark>
                  {match.after}
                </>
              ) : (
                text
              )}
            </p>
            {text.length >= 1500 && (
              <span className="text-xs text-muted">Excerpt: the first 1,500 characters of the source.</span>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
};
