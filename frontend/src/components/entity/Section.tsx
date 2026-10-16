import React from 'react';

export const Section: React.FC<{
  title: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
}> = ({ title, meta, children, id }) => (
  <section aria-labelledby={id ? `${id}-title` : undefined} aria-label={id ? undefined : title} id={id} className="flex flex-col rounded-panel border border-divider">
    <div className="flex min-h-9 items-center justify-between gap-2 border-b border-divider px-3">
      <h2 id={id ? `${id}-title` : undefined} className="m-0 text-sm font-medium">
        {title}
      </h2>
      {meta && <span className="text-xs text-muted">{meta}</span>}
    </div>
    <div className="min-w-0">{children}</div>
  </section>
);
