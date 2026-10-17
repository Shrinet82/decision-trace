import React from 'react';
import { Link } from 'react-router-dom';
import { btnOutline } from '../ui';

export const ListSkeleton: React.FC<{ label: string }> = ({ label }) => (
  <div role="status" aria-label={label} className="flex flex-col">
    {Array.from({ length: 8 }).map((_, i) => (
      <div key={i} className="flex h-11 items-center gap-3 border-b border-row-divider px-5">
        <div className="skeleton h-3.5 w-3.5 rounded-full" />
        <div className="skeleton h-3 w-40" />
        <div className="skeleton ml-auto h-3 w-24" />
      </div>
    ))}
  </div>
);

export const DetailSkeleton: React.FC<{ label: string }> = ({ label }) => (
  <div role="status" aria-label={label} className="flex flex-col gap-3 px-5 py-6 min-[900px]:px-8">
    <div className="skeleton h-6 w-1/3" />
    <div className="skeleton h-4 w-1/2" />
    <div className="skeleton mt-3 h-48 w-full" />
  </div>
);

export const LoadError: React.FC<{
  notFound: boolean;
  what: string;
  message?: string;
  backTo: string;
  backLabel: string;
  onRetry?: () => void;
}> = ({ notFound, what, message, backTo, backLabel, onRetry }) => (
  <div role={notFound ? 'status' : 'alert'} className="m-5 flex flex-col items-start gap-2 rounded-panel border border-divider bg-subtle p-4">
    <h1 className="m-0 text-lg font-semibold">{notFound ? `${what} not found` : `Could not load ${what.toLowerCase()}`}</h1>
    {message && <p className="m-0 text-muted">{message}</p>}
    <div className="flex flex-wrap gap-2">
      {!notFound && onRetry && (
        <button type="button" className={btnOutline} onClick={onRetry}>
          Retry
        </button>
      )}
      <Link to={backTo} className={btnOutline}>
        {backLabel}
      </Link>
    </div>
  </div>
);

/** A failed load: what happened, in plain words, and a button to try again. */
export const ErrorNotice: React.FC<{ title: string; message?: string; onRetry?: () => void; className?: string }> = ({
  title,
  message,
  onRetry,
  className = 'm-5',
}) => (
  <div
    role="alert"
    className={`${className} flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg p-3`}
  >
    <span className="font-medium text-status-conflict-text">{title}</span>
    {message && <span className="text-text-2">{message}</span>}
    {onRetry && (
      <button type="button" className={btnOutline} onClick={onRetry}>
        Retry
      </button>
    )}
  </div>
);
