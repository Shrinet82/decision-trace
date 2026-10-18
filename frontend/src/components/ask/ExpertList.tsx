import React from 'react';
import { Link } from '../../router';
import type { Expert } from '../../api/types';
import { EVIDENCE, evidenceSummary } from '../../utils/expertise';
import { personHref } from '../../utils/links';
import { Avatar } from '../Avatar';
import { LeftBadge } from '../entity/Badge';

/**
 * People ranked by recorded evidence. Each bar is made of the real counts (one segment per kind,
 * length = count x weight), so it shows what the ranking is based on rather than a made-up score.
 */
export const ExpertList: React.FC<{ experts: Expert[]; subject?: string; limit?: number }> = ({
  experts,
  subject,
  limit = 8,
}) => {
  const shown = experts.slice(0, limit);
  const max = Math.max(1, ...shown.map((e) => e.score));
  return (
    <section aria-label="People ranked by evidence" className="flex flex-col rounded-panel border border-divider">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-divider px-3 py-1.5">
        <h3 className="m-0 text-sm font-medium">Who knows {subject ?? 'this'}</h3>
        <ul aria-label="Evidence weights" className="m-0 flex list-none flex-wrap gap-x-3 gap-y-0.5 p-0 text-xs text-muted">
          {EVIDENCE.map((k) => (
            <li key={k.key} className="inline-flex items-center gap-1">
              <span aria-hidden="true" className="inline-block h-2 w-2 rounded-[2px]" style={{ background: k.color }} />
              {k.plural} ×{k.weight}
            </li>
          ))}
        </ul>
      </div>
      {shown.length === 0 ? (
        <p className="m-0 px-3 py-2.5 text-muted">No one has recorded evidence on this.</p>
      ) : (
        <ol className="m-0 list-none p-0">
          {shown.map((e, i) => (
            <li
              key={e.name}
              className="evidence-row-in flex flex-col gap-1.5 border-b border-row-divider px-3 py-2 last:border-b-0"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="w-4 shrink-0 text-right tabular-nums text-xs text-muted">{i + 1}</span>
                <Avatar name={e.name} size={18} active={!e.departed} />
                <Link to={personHref(e.name)} className="font-medium hover:underline">
                  {e.name}
                </Link>
                {e.role && <span className="hidden text-xs text-muted sm:inline">{e.role}</span>}
                {e.departed && <LeftBadge leaveDate={e.leave_date} />}
                <span className="ml-auto text-xs text-muted">{evidenceSummary(e)}</span>
              </div>
              <div
                role="img"
                aria-label={`${e.name}: ${evidenceSummary(e)} (weighted ${e.score})`}
                className="ml-6 flex h-2 overflow-hidden rounded-full bg-hover"
              >
                {EVIDENCE.map((k) =>
                  e.evidence[k.key] > 0 ? (
                    <span
                      key={k.key}
                      style={{ width: `${((e.evidence[k.key] * k.weight) / max) * 100}%`, background: k.color }}
                    />
                  ) : null
                )}
              </div>
              {e.decisions.length > 0 && (
                <span className="ml-6 text-xs text-muted">Decided {e.decisions.join(', ')}</span>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};
