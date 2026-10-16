import React from 'react';
import { getSystemLine } from '../config/lines';

export const SystemSquare: React.FC<{ system?: string | null; size?: number }> = ({
  system,
  size = 8,
}) => (
  <span
    aria-hidden="true"
    className="inline-block shrink-0 rounded-[2px]"
    style={{ width: size, height: size, background: getSystemLine(system).color }}
  />
);

export const SystemChip: React.FC<{
  system: string;
  /** System whose category colour to use when the label differs (e.g. "Snowflake +1"). */
  colorFrom?: string;
  className?: string;
}> = ({ system, colorFrom, className = '' }) => (
  <span
    className={`inline-flex h-[22px] max-w-[160px] items-center gap-1.5 rounded-chip border border-border px-2 text-xs text-text-2 ${className}`}
  >
    <SystemSquare system={colorFrom ?? system} size={7} />
    <span className="truncate">{system}</span>
  </span>
);
