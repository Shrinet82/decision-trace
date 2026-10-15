import React from 'react';
import type { HealthStatus } from '../api/types';

export interface StatusMarkerProps {
  health: HealthStatus | string;
  healthReason?: string;
  lineColor?: string;
  showLabel?: boolean;
  size?: number; // default 16
  className?: string;
}

const HEALTH_LABELS: Record<string, string> = {
  active: 'Active',
  superseded: 'Superseded',
  contradicted: 'Contradicted',
  possibly_stale: 'Possibly stale',
};

export const StatusMarker: React.FC<StatusMarkerProps> = ({
  health,
  healthReason,
  lineColor = 'var(--line-platform)',
  showLabel = true,
  size = 16,
  className = '',
}) => {
  const normalizedHealth = (health || 'active').toLowerCase() as HealthStatus;
  const label = HEALTH_LABELS[normalizedHealth] || 'Active';
  const tooltipText = healthReason ? `${label}: ${healthReason}` : label;

  const renderIcon = () => {
    switch (normalizedHealth) {
      case 'active':
        // Filled circle in the decision's line color
        return (
          <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            className="shrink-0"
            aria-hidden="true"
          >
            <circle
              cx="8"
              cy="8"
              r="6"
              fill={lineColor}
              stroke="var(--color-surface)"
              strokeWidth="1.5"
            />
          </svg>
        );

      case 'superseded':
        // Hollow grey circle with a diagonal strike
        return (
          <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            className="shrink-0"
            aria-hidden="true"
          >
            <circle
              cx="8"
              cy="8"
              r="6"
              fill="none"
              stroke="var(--color-text-muted)"
              strokeWidth="1.5"
            />
            <line
              x1="3.5"
              y1="12.5"
              x2="12.5"
              y2="3.5"
              stroke="var(--color-text-muted)"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        );

      case 'contradicted':
        // Circle split in half with a danger-colored border
        return (
          <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            className="shrink-0"
            aria-hidden="true"
          >
            <defs>
              <clipPath id="split-half">
                <rect x="0" y="0" width="8" height="16" />
              </clipPath>
            </defs>
            {/* Left filled half */}
            <circle
              cx="8"
              cy="8"
              r="6"
              fill="var(--color-danger)"
              clipPath="url(#split-half)"
            />
            {/* Outer border */}
            <circle
              cx="8"
              cy="8"
              r="6"
              fill="none"
              stroke="var(--color-danger)"
              strokeWidth="1.5"
            />
            {/* Dividing center line */}
            <line
              x1="8"
              y1="2"
              x2="8"
              y2="14"
              stroke="var(--color-danger)"
              strokeWidth="1.5"
            />
          </svg>
        );

      case 'possibly_stale':
        // Dashed circle outline
        return (
          <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            className="shrink-0"
            aria-hidden="true"
          >
            <circle
              cx="8"
              cy="8"
              r="6"
              fill="none"
              stroke="var(--color-warning)"
              strokeWidth="1.5"
              strokeDasharray="2.5 2"
            />
          </svg>
        );

      default:
        return (
          <svg
            width={size}
            height={size}
            viewBox="0 0 16 16"
            className="shrink-0"
            aria-hidden="true"
          >
            <circle cx="8" cy="8" r="6" fill={lineColor} />
          </svg>
        );
    }
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs text-text ${className}`}
      title={tooltipText}
      role="status"
      aria-label={tooltipText}
    >
      {renderIcon()}
      {showLabel && <span className="font-normal select-none">{label}</span>}
    </span>
  );
};
