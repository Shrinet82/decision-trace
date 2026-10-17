import React from 'react';
import { Link } from 'react-router-dom';
import { decisionHref } from '../../utils/links';
import type { DecisionDetail } from '../../api/types';
import { formatLongDate } from '../../utils/format';
import {
  healthToStatus,
  STATUS_LABEL,
  validityChecks,
} from '../../utils/model';
import { Avatar } from '../Avatar';
import { PropertyList, Property, SidePanel } from '../PageFrame';
import { StatusIcon } from '../StatusIcon';
import { SystemSquare } from '../SystemMark';

export interface AskPropertiesProps {
  detail: DecisionDetail | undefined;
  loading: boolean;
  /** Shown at the top of the panel (the "How I found this" trace). */
  before?: React.ReactNode;
  /** Replaces the "ask a question" hint when an answer has no primary decision. */
  emptyText?: string;
}

const None = () => <span className="text-muted">None</span>;

export const AskProperties: React.FC<AskPropertiesProps> = ({ detail, loading, before, emptyText }) => {
  const top = before ? (
    <>
      {before}
      <div className="h-px bg-divider" />
    </>
  ) : null;
  if (loading) {
    return (
      <SidePanel label="Decision properties">
        {top}
        <div className="skeleton h-4 w-24" />
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-5/6" />
        <div className="skeleton h-4 w-2/3" />
      </SidePanel>
    );
  }

  if (!detail) {
    return (
      <SidePanel label="Decision properties">
        {top}
        <div className="font-semibold">Decision properties</div>
        <p className="m-0 text-muted">
          {emptyText ??
            'Ask a question to see the status, owner, and validity checks of the decision behind the answer.'}
        </p>
      </SidePanel>
    );
  }

  const status = healthToStatus(detail.health);
  const checks = validityChecks(detail);

  return (
    <SidePanel label="Decision properties">
      {top}
      <div className="flex flex-col gap-1">
        {detail.decision_code && <div className="text-xs text-muted">{detail.decision_code}</div>}
        <Link to={decisionHref(detail.decision_code ?? detail.id)} className="font-semibold hover:underline">
          {detail.title}
        </Link>
      </div>
      <PropertyList>
        <Property label="Status">
          <StatusIcon status={status} size={13} />
          {STATUS_LABEL[status]}
        </Property>
        {detail.decided_by && (
          <Property label="Decided by">
            <Avatar name={detail.decided_by} size={18} />
            <span className="min-w-0">{detail.decided_by}</span>
          </Property>
        )}
        {detail.decided_on && <Property label="Date">{formatLongDate(detail.decided_on) || detail.decided_on}</Property>}
        {detail.systems.length > 0 && (
          <Property label="System">
            <SystemSquare system={detail.systems[0]} />
            <span className="min-w-0">{detail.systems.join(', ')}</span>
          </Property>
        )}
        <Property label="Supersedes">
          {detail.supersedes.length > 0 ? detail.supersedes.join('; ') : <None />}
        </Property>
        <Property label="Conflicts">
          {detail.contradicts.length > 0 ? detail.contradicts.join('; ') : <None />}
        </Property>
      </PropertyList>
      <div className="h-px bg-divider" />
      <div className="flex flex-col gap-2">
        <div className="text-muted">Validity checks</div>
        {checks.map((check) => (
          <div key={check.label} className="flex items-start gap-2">
            <span
              aria-hidden="true"
              className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${
                check.ok ? 'bg-status-active' : 'bg-status-stale'
              }`}
            />
            {check.label}
          </div>
        ))}
      </div>
    </SidePanel>
  );
};
