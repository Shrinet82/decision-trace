import React from 'react';
import { Link } from 'react-router-dom';
import { useSource } from '../api/hooks';
import type { SourceKind } from '../api/types';
import { formatLongDate } from '../utils/format';
import { SOURCE_KIND_LABEL } from '../utils/sources';
import { highlightAll } from '../utils/highlight';
import { decisionHref, personHref, systemHref } from '../utils/links';
import { healthToStatus } from '../utils/model';
import { Avatar } from './Avatar';
import { Badge, LeftBadge } from './entity/Badge';
import { Drawer } from './Drawer';
import { StatusIcon } from './StatusIcon';
import { SystemSquare } from './SystemMark';

const recordHref = (label: string, name: string) =>
  label === 'Person' ? personHref(name) : label === 'System' ? systemHref(name) : null;

/** One source: its full text with every linked decision's quote highlighted, or a record's fields. */
export const SourceDocDrawer: React.FC<{
  open: { kind: SourceKind; key: string } | null;
  onClose: () => void;
}> = ({ open, onClose }) => {
  const query = useSource(open?.kind, open?.key);
  const doc = query.data;
  const quotes = doc?.decisions.map((d) => d.quote) ?? [];
  const segments = doc?.text ? highlightAll(doc.text, quotes) : [];
  const found = new Set(segments.filter((s) => s.quote !== undefined).map((s) => s.quote));

  return (
    <Drawer open={Boolean(open)} onClose={onClose} title="Source" titleId="source-doc-title">
      {open && (
        <div className="flex flex-col gap-5 p-4">
          {query.isLoading && (
            <div role="status" aria-label="Loading source" className="flex flex-col gap-2">
              <div className="skeleton h-4 w-32" />
              <div className="skeleton h-24 w-full" />
            </div>
          )}
          {query.isError && <p role="alert" className="m-0 text-status-conflict-text">{query.error.message}</p>}
          {doc && (
            <>
              <div className="flex flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2 font-medium text-text">
                  {doc.kind === 'ticket' ? doc.key : doc.title}
                  {doc.demo && <Badge tone="accent">Demo ingest</Badge>}
                  {doc.status && doc.status !== 'closed' && doc.kind === 'ticket' && <Badge tone="stale">{doc.status}</Badge>}
                </span>
                <span className="text-xs text-muted">
                  {SOURCE_KIND_LABEL[doc.kind]}
                  {doc.date && ` · ${formatLongDate(doc.date) || doc.date}`}
                  {doc.kind === 'ticket' && doc.status && ` · ${doc.status}`}
                </span>
                {doc.kind === 'ticket' && doc.title !== doc.key && <span className="text-text-2">{doc.title}</span>}
              </div>

              {doc.text && (
                <section aria-label="Source text" className="flex flex-col gap-1.5">
                  <h3 className="m-0 text-xs font-medium text-muted">
                    Text{found.size > 0 ? ` · ${found.size} ${found.size === 1 ? 'quote' : 'quotes'} highlighted` : ''}
                  </h3>
                  <p
                    data-testid="source-doc-text"
                    className="m-0 whitespace-pre-wrap break-words rounded-panel border border-divider px-3 py-2.5 leading-[1.6] text-text-2"
                  >
                    {segments.map((s, i) =>
                      s.quote !== undefined ? (
                        <mark key={i} className="rounded-[3px] bg-[#FCEFC7] px-0.5 text-text">
                          {s.text}
                        </mark>
                      ) : (
                        <React.Fragment key={i}>{s.text}</React.Fragment>
                      )
                    )}
                  </p>
                  {doc.text.length >= 1500 && (
                    <span className="text-xs text-muted">Excerpt: the first 1,500 characters of the source.</span>
                  )}
                </section>
              )}

              {Object.keys(doc.fields).length > 0 && (
                <section aria-label="Record fields" className="flex flex-col gap-1.5">
                  <h3 className="m-0 text-xs font-medium text-muted">Fields (company.db)</h3>
                  <dl className="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-y-1.5 rounded-panel border border-divider px-3 py-2.5">
                    {Object.entries(doc.fields).map(([k, v]) => (
                      <React.Fragment key={k}>
                        <dt className="text-muted">{k.replace(/_/g, ' ')}</dt>
                        <dd className="m-0 break-words">{String(v)}</dd>
                      </React.Fragment>
                    ))}
                  </dl>
                </section>
              )}

              <section aria-label="Linked decisions" className="flex flex-col gap-1.5">
                <h3 className="m-0 text-xs font-medium text-muted">Linked decisions ({doc.decisions.length})</h3>
                {doc.decisions.length === 0 ? (
                  <p className="m-0 text-muted">No decision is based on this source.</p>
                ) : (
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {doc.decisions.map((d) => (
                      <li key={d.id} className="flex flex-col gap-1 rounded-panel border border-divider px-3 py-2">
                        <span className="flex min-w-0 items-center gap-2">
                          <StatusIcon status={healthToStatus(d.health)} />
                          <Link to={decisionHref(d.decision_code ?? d.id)} className="min-w-0 truncate font-medium hover:underline">
                            {d.decision_code && <span className="mr-1.5 font-normal text-muted">{d.decision_code}</span>}
                            {d.title}
                          </Link>
                        </span>
                        {d.quote && <blockquote className="m-0 pl-[22px] text-text-2">“{d.quote}”</blockquote>}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {doc.people.length > 0 && (
                <section aria-label="People" className="flex flex-col gap-1.5">
                  <h3 className="m-0 text-xs font-medium text-muted">People</h3>
                  <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                    {doc.people.map((p) => (
                      <li key={p.name} className="flex flex-wrap items-center gap-2">
                        <Avatar name={p.name} size={18} active={!p.departed} />
                        <Link to={personHref(p.name)} className="font-medium hover:underline">{p.name}</Link>
                        <span className="text-xs text-muted">{p.relation}</span>
                        {p.departed && <LeftBadge />}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {(doc.systems.length > 0 || doc.related.length > 0) && (
                <section aria-label="Connected" className="flex flex-col gap-1.5">
                  <h3 className="m-0 text-xs font-medium text-muted">{doc.systems.length ? 'Systems mentioned' : 'Connected to'}</h3>
                  <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                    {doc.systems.map((s) => (
                      <li key={s}>
                        <Link to={systemHref(s)} className="inline-flex h-[22px] items-center gap-1.5 rounded-chip border border-border px-2 text-xs hover:bg-subtle">
                          <SystemSquare system={s} />
                          {s}
                        </Link>
                      </li>
                    ))}
                    {doc.related.map((r) => {
                      const href = recordHref(r.label, r.name);
                      const label = `${r.name} · ${r.relation.replace(/_/g, ' ')}`;
                      return (
                        <li key={`${r.label}:${r.name}:${r.relation}`}>
                          {href ? (
                            <Link to={href} className="inline-flex h-[22px] items-center rounded-chip border border-border px-2 text-xs hover:bg-subtle">{label}</Link>
                          ) : (
                            <span className="inline-flex h-[22px] items-center rounded-chip border border-border px-2 text-xs">{label}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      )}
    </Drawer>
  );
};
