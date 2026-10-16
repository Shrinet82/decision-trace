import React from 'react';
import { getAvatarTone, getInitials } from '../utils/format';

export interface AvatarProps {
  name?: string | null;
  /** Tooltip; defaults to the name. */
  title?: string;
  size?: number;
  /** Inactive people (left the company) render in a muted tone. */
  active?: boolean;
  className?: string;
}

export const Avatar: React.FC<AvatarProps> = ({ name, title, size = 22, active = true, className = '' }) => {
  const tone = getAvatarTone(name, active);
  return (
    <span
      title={title ?? name ?? undefined}
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${className}`}
      style={{
        width: size,
        height: size,
        background: tone.bg,
        color: tone.fg,
        fontSize: Math.max(8, Math.round(size * 0.41)),
      }}
    >
      {getInitials(name)}
    </span>
  );
};
