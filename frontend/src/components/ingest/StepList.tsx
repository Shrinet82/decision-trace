import React from 'react';
import type { StepDisplayStatus, StepState } from '../../utils/ingestRun';
import { StatusIcon } from '../StatusIcon';

const STATUS_TEXT: Record<StepDisplayStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  done: 'Done',
  skipped: 'Skipped',
  error: 'Failed',
};

/** Static state glyphs (no spinners): ring, accent ring with dot, check, minus, red alert. */
export const StepIcon: React.FC<{ status: StepDisplayStatus }> = ({ status }) => {
  if (status === 'done') return <StatusIcon status="active" />;
  if (status === 'error') return <StatusIcon status="conflict" />;
  return (
    <svg width={14} height={14} viewBox="0 0 14 14" aria-hidden="true" focusable="false">
      {status === 'pending' && (
        <circle cx="7" cy="7" r="5.6" fill="none" stroke="#8A8E95" strokeWidth="1.4" />
      )}
      {status === 'running' && (
        <>
          <circle cx="7" cy="7" r="5.6" fill="none" stroke="#4F5BD5" strokeWidth="1.6" />
          <circle cx="7" cy="7" r="2.4" fill="#4F5BD5" />
        </>
      )}
      {status === 'skipped' && (
        <>
          <circle cx="7" cy="7" r="5.6" fill="none" stroke="#9A9DA4" strokeWidth="1.4" />
          <path d="M4.6 7h4.8" stroke="#6B6F76" strokeWidth="1.6" strokeLinecap="round" />
        </>
      )}
    </svg>
  );
};

export const StepList: React.FC<{ steps: StepState[] }> = ({ steps }) => (
  <ol aria-label="Ingest steps" className="m-0 flex list-none flex-col p-0">
    {steps.map((s) => (
      <li
        key={s.key}
        data-step={s.key}
        data-step-status={s.status}
        aria-current={s.status === 'running' ? 'step' : undefined}
        className="flex items-start gap-2.5 border-b border-row-divider px-3 py-2 last:border-b-0"
      >
        <span className="mt-[3px] inline-flex shrink-0">
          <StepIcon status={s.status} />
        </span>
        <span className="flex min-w-0 flex-col">
          <span
            className={
              s.status === 'pending' || s.status === 'skipped'
                ? 'text-muted'
                : s.status === 'error'
                  ? 'font-medium text-status-conflict-text'
                  : s.status === 'running'
                    ? 'font-medium text-text'
                    : 'text-text'
            }
          >
            <span className="sr-only">{STATUS_TEXT[s.status]}: </span>
            {s.label}
          </span>
          {s.detail && <span className="break-words text-xs text-muted">{s.detail}</span>}
        </span>
      </li>
    ))}
  </ol>
);
