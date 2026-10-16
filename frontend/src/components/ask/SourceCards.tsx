import React from 'react';
import type { Citation } from '../../api/types';
import { formatLongDate } from '../../utils/format';
import { evidenceQuoteForSource, type GraphIndex } from '../../utils/model';
import { citeAnchor } from '../../utils/answer';

const TYPE_LABEL: Record<Citation['type'], string> = {
  ticket: 'Ticket',
  meeting: 'Meeting notes',
  decision: 'Decision',
  document: 'Document',
};

export interface SourceCardsProps {
  citations: Citation[];
  turnKey: string;
  index: GraphIndex | undefined;
}

export const SourceCards: React.FC<SourceCardsProps> = ({ citations, turnKey, index }) => (
  <section aria-label="Sources" className="flex flex-col gap-2">
    <h2 className="m-0 text-xs font-medium text-muted">Sources</h2>
    {citations.map((citation, i) => {
      const node = index?.find(citation.id) ?? index?.find(citation.title);
      const props = node?.properties ?? {};
      const date = formatLongDate(
        (props.closed as string) || (props.opened as string) || (props.date as string) || undefined
      );
      const quote = index && node ? evidenceQuoteForSource(index, node.id) : null;
      return (
        <div
          key={`${citation.id}-${i}`}
          id={citeAnchor(turnKey, i)}
          tabIndex={-1}
          className="flex gap-2.5 rounded-panel border border-divider px-3 py-2.5 scroll-mt-16 target:bg-selected"
        >
          <span className="text-xs font-semibold text-accent">{i + 1}</span>
          <div className="flex min-w-0 flex-col gap-1">
            <div>
              <span className="font-medium">{citation.id}</span>
              <span className="text-muted">
                {' '}
                · {TYPE_LABEL[citation.type]}
                {date && ` · ${date}`}
              </span>
            </div>
            {citation.title !== citation.id && <div className="text-muted">{citation.title}</div>}
            {quote && <div className="text-text-2">“{quote}”</div>}
          </div>
        </div>
      );
    })}
  </section>
);
