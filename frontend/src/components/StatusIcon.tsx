import React from 'react';
import type { StatusKind } from '../utils/model';
import { STATUS_LABEL } from '../utils/model';
import { STATUS_SVG_INNER } from '../utils/statusSvg';

export interface StatusIconProps {
  status: StatusKind;
  size?: number;
  /** When true the icon is exposed to assistive tech with the status name. */
  labelled?: boolean;
  className?: string;
}

export const StatusIcon: React.FC<StatusIconProps> = ({
  status,
  size = 14,
  labelled = false,
  className,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 14 14"
    className={className}
    role={labelled ? 'img' : undefined}
    aria-label={labelled ? STATUS_LABEL[status] : undefined}
    aria-hidden={labelled ? undefined : true}
    focusable="false"
    dangerouslySetInnerHTML={{ __html: STATUS_SVG_INNER[status] }}
  />
);
