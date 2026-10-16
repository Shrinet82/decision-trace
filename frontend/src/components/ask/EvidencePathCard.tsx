import React from 'react';
import { Link } from 'react-router-dom';
import { decisionHref, personHref, systemHref } from '../../utils/links';
import type { EvidencePath, EvidenceRow } from '../../utils/evidence';
import type { StatusKind } from '../../utils/model';
import { Avatar } from '../Avatar';
import { StatusIcon } from '../StatusIcon';
import { SystemSquare } from '../SystemMark';

export interface EvidencePathCardProps {
  path: EvidencePath;
  /** Status of a decision node by id (health), used for decision rows. */
  statusOf: (nodeId: string) => StatusKind;
}

const RowIcon: React.FC<{ row: EvidenceRow; status: StatusKind }> = ({ row, status }) => {
  if (row.kind === 'Decision') return <StatusIcon status={status} />;
  if (row.kind === 'System') return <SystemSquare system={row.name} />;
  if (row.kind === 'Person') return <Avatar name={row.name} size={16} />;
  return <span aria-hidden="true" className="inline-block h-2 w-2 rounded-[2px] bg-faint" />;
};

const Connector: React.FC<{ label: string | null }> = ({ label }) => (
  <li aria-hidden={label ? undefined : true} className="flex h-[22px] items-center gap-2.5 px-3 text-xs text-muted">
    <span className="flex w-[18px] justify-center">
      <span className="h-[22px] w-px bg-[#D8DAE0]" />
    </span>
    {label}
  </li>
);

export const EvidencePathCard: React.FC<EvidencePathCardProps> = ({ path, statusOf }) => {
  const { rows } = path;
  const mainIndex = rows.findIndex((r) => r.isMain);

  return (
    <section aria-label="Evidence path" className="flex flex-col rounded-panel border border-divider">
      <div className="flex h-9 items-center justify-between border-b border-divider px-3 font-medium">
        Evidence path
        <span className="text-xs font-normal text-muted">
          {rows.length} nodes, {path.edgeCount} edges
        </span>
      </div>
      <ol className="m-0 flex list-none flex-col py-1.5 pl-0">
        {rows.map((row, i) => {
          const status = row.kind === 'Decision' ? statusOf(row.nodeId) : 'active';
          const isOld = row.kind === 'Decision' && status === 'superseded';
          // The connector between two rows carries the relation of the row farther
          // from the main decision: above it, the row above; below it, the row below.
          const connectorLabel =
            i === 0
              ? null
              : i <= mainIndex
                ? rows[i - 1].relation
                : row.relation;
          return (
            <React.Fragment key={`${row.nodeId}-${i}`}>
              {i > 0 && <Connector label={connectorLabel} />}
              <li
                aria-current={row.isMain ? 'true' : undefined}
                className={`flex min-h-[34px] min-w-0 items-center gap-x-2.5 px-3 ${row.isMain ? 'bg-selected' : ''}`}
              >
                <span className="flex w-[18px] justify-center">
                  <RowIcon row={row} status={status} />
                </span>
                <span className="w-16 shrink-0 text-muted">{row.kind}</span>
                {(() => {
                  const fullName = row.code ? `${row.code} ${row.name}` : row.name;
                  const href =
                    row.kind === 'Decision'
                      ? decisionHref(row.code ?? row.nodeId)
                      : row.kind === 'System'
                        ? systemHref(row.name)
                        : row.kind === 'Person'
                          ? personHref(row.name)
                          : null;
                  const nameClass = `min-w-0 truncate ${
                    row.isMain ? 'font-semibold' : isOld ? 'font-medium text-muted line-through' : 'font-medium'
                  }`;
                  const content = (
                    <>
                      {row.code && <span className="mr-1.5 font-normal text-muted">{row.code}</span>}
                      {row.name}
                    </>
                  );
                  // Long titles truncate with an ellipsis; the full text is in the tooltip
                  return href ? (
                    <Link to={href} title={fullName} className={`${nameClass} hover:underline`}>
                      {content}
                    </Link>
                  ) : (
                    <span title={fullName} className={nameClass}>
                      {content}
                    </span>
                  );
                })()}
                {row.detail && (
                  <span title={row.detail} className="min-w-0 flex-1 truncate text-muted max-sm:hidden">
                    {row.detail}
                  </span>
                )}
              </li>
            </React.Fragment>
          );
        })}
      </ol>
    </section>
  );
};
