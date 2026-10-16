import React from 'react';

const TONES = {
  neutral: 'border-border text-text-2',
  stale: 'border-[#EBD3A6] bg-[#FDF8EE] text-status-stale-text',
  conflict: 'border-status-conflict-border bg-status-conflict-bg text-status-conflict-text',
} as const;

export const Badge: React.FC<{
  tone?: keyof typeof TONES;
  title?: string;
  children: React.ReactNode;
}> = ({ tone = 'neutral', title, children }) => (
  <span
    title={title}
    className={`inline-flex h-5 shrink-0 items-center whitespace-nowrap rounded-chip border px-2 text-[11px] font-medium ${TONES[tone]}`}
  >
    {children}
  </span>
);

/** "Left company" marker for departed people. */
export const LeftBadge: React.FC<{ leaveDate?: string | null }> = ({ leaveDate }) => (
  <Badge tone="stale" title={leaveDate ? `Left on ${leaveDate}` : 'Has left the company'}>
    Left company
  </Badge>
);
