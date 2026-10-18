import React from 'react';
import { Link } from '../../router';
import type { DecisionRef } from '../../api/types';
import { formatLongDate } from '../../utils/format';
import { decisionHref } from '../../utils/links';
import { healthToStatus, STATUS_LABEL } from '../../utils/model';
import { StatusIcon } from '../StatusIcon';

export interface DecisionTimelineProps {
  items: DecisionRef[];
  /** Decision to highlight (the page's own decision). */
  currentId?: string;
  emptyText?: string;
  /** Show decider names under each title. */
  showDeciders?: boolean;
}

/** Vertical, oldest-first list of decisions with a connecting rail. */
export const DecisionTimeline: React.FC<DecisionTimelineProps> = ({
  items,
  currentId,
  emptyText = 'No decisions recorded.',
  showDeciders = true,
}) => {
  if (items.length === 0) return <p className="m-0 px-3 py-4 text-muted">{emptyText}</p>;
  return (
    <ol className="m-0 list-none py-1.5 pl-0">
      {items.map((d, i) => {
        const status = healthToStatus(d.health);
        const current = d.id === currentId;
        return (
          <li key={d.id} className="relative">
            {i < items.length - 1 && (
              <span aria-hidden="true" className="absolute left-[19px] top-[26px] h-[calc(100%-14px)] w-px bg-[#D8DAE0]" />
            )}
            <Link
              to={decisionHref(d.decision_code ?? d.id)}
              aria-current={current ? 'page' : undefined}
              className={`flex items-start gap-2.5 px-3 py-2 transition-colors hover:bg-subtle ${current ? 'bg-selected hover:bg-selected' : ''}`}
            >
              <span className="relative z-[1] mt-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-surface">
                <StatusIcon status={status} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="flex min-w-0 items-baseline gap-2">
                  <span className="shrink-0 text-muted">{d.decision_code}</span>
                  <span className={`min-w-0 truncate ${current ? 'font-semibold' : 'font-medium'}`} title={d.title}>
                    {d.title}
                  </span>
                </span>
                <span className="text-xs text-muted">
                  {formatLongDate(d.decided_on) || 'Undated'} · {STATUS_LABEL[status]}
                  {showDeciders && d.deciders.length > 0 && ` · ${d.deciders.join(', ')}`}
                </span>
              </span>
              {current && <span className="shrink-0 text-xs font-medium text-accent">This decision</span>}
            </Link>
          </li>
        );
      })}
    </ol>
  );
};
