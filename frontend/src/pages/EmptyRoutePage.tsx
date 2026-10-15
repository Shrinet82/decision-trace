import React from 'react';

export interface EmptyRoutePageProps {
  title: string;
  description: string;
}

export const EmptyRoutePage: React.FC<EmptyRoutePageProps> = ({
  title,
  description,
}) => {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-text tracking-tight">
          {title}
        </h1>
        <p className="mt-1 text-sm text-text-muted">{description}</p>
      </div>

      <div className="p-8 border border-border rounded-panel bg-surface text-center space-y-3">
        <h2 className="text-base font-semibold text-text">
          {title} explorer view
        </h2>
        <p className="text-sm text-text-muted max-w-md mx-auto">
          This section will be populated in subsequent frontend steps. Use the Ask page to query decisions, rationale, owners, and evidence paths.
        </p>
      </div>
    </div>
  );
};
