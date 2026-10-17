import React from 'react';
import { Link } from 'react-router-dom';
import type { AnswerSection, SectionItem } from '../../api/types';
import { formatLongDate } from '../../utils/format';
import { decisionHref, personHref, sourceHref, systemHref } from '../../utils/links';
import { healthToStatus } from '../../utils/model';
import { Avatar } from '../Avatar';
import { Badge, LeftBadge } from '../entity/Badge';
import { StatusIcon } from '../StatusIcon';
import { SystemSquare } from '../SystemMark';

function hrefFor(item: SectionItem): string | null {
  switch (item.kind) {
    case 'decision':
      return decisionHref(item.code ?? item.id ?? item.name);
    case 'person':
      return personHref(item.name);
    case 'system':
      return systemHref(item.name);
    case 'ticket':
    case 'meeting':
      return sourceHref(item.kind, item.name);
    default:
      return null;
  }
}

const ItemIcon: React.FC<{ item: SectionItem }> = ({ item }) => {
  if (item.kind === 'decision') return <StatusIcon status={healthToStatus(item.health ?? 'active')} />;
  if (item.kind === 'person') return <Avatar name={item.name} size={16} active={!item.departed} />;
  if (item.kind === 'system') return <SystemSquare system={item.name} />;
  return <span aria-hidden="true" className="inline-block h-2 w-2 rounded-[2px] bg-faint" />;
};

const Row: React.FC<{ item: SectionItem; index: number }> = ({ item, index }) => {
  const href = hrefFor(item);
  const label = (
    <>
      {item.code && <span className="mr-1.5 font-normal text-muted">{item.code}</span>}
      {item.name}
    </>
  );
  const title = item.code ? `${item.code} ${item.name}` : item.name;
  return (
    <li
      className="evidence-row-in flex min-h-[34px] flex-wrap items-center gap-x-2.5 gap-y-0.5 border-b border-row-divider px-3 py-1.5 last:border-b-0"
      style={{ animationDelay: `${Math.min(index, 10) * 40}ms` }}
    >
      <span className="flex w-[18px] shrink-0 justify-center">
        <ItemIcon item={item} />
      </span>
      {href ? (
        <Link to={href} title={title} className="min-w-0 max-w-full truncate font-medium hover:underline">
          {label}
        </Link>
      ) : (
        <span title={title} className="min-w-0 max-w-full truncate font-medium">
          {label}
        </span>
      )}
      {item.departed && <LeftBadge leaveDate={item.leave_date} />}
      {item.kind === 'ticket' && item.status && item.status.toLowerCase() !== 'closed' && (
        <Badge tone="stale">{item.status}</Badge>
      )}
      {(item.detail || item.date) && (
        <span className="min-w-0 basis-full truncate pl-7 text-xs text-muted sm:basis-auto sm:flex-1 sm:pl-0">
          {item.detail}
          {item.kind === 'ticket' && item.date && ` · ${formatLongDate(item.date) || item.date}`}
        </span>
      )}
    </li>
  );
};

/** Grouped results of an impact or status question: one card per group, every item linked. */
export const AnswerSections: React.FC<{ sections: AnswerSection[]; label: string }> = ({ sections, label }) => (
  <section aria-label={label} className="flex flex-col gap-3">
    {sections.map((s) => (
      <section
        key={s.key}
        aria-label={`${s.title}, ${s.total}`}
        className="flex flex-col rounded-panel border border-divider"
      >
        <h3 className="m-0 flex h-9 items-center justify-between border-b border-divider px-3 text-sm font-medium">
          {s.title}
          <span className="text-xs font-normal text-muted">{s.total}</span>
        </h3>
        {s.items.length === 0 ? (
          <p className="m-0 px-3 py-2.5 text-muted">None</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {s.items.map((item, i) => (
              <Row key={`${item.kind}:${item.id ?? item.name}`} item={item} index={i} />
            ))}
          </ul>
        )}
        {s.items.length < s.total && (
          <p className="m-0 border-t border-divider px-3 py-1.5 text-xs text-muted">
            Showing {s.items.length} of {s.total}
          </p>
        )}
      </section>
    ))}
  </section>
);
