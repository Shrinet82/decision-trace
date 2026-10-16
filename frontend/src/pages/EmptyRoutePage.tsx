import React from 'react';
import { PageFrame } from '../components/PageFrame';

interface EmptyRoutePageProps {
  title: string;
  description: string;
}

export const EmptyRoutePage: React.FC<EmptyRoutePageProps> = ({ title, description }) => (
  <PageFrame header={<span className="font-medium text-text">{title}</span>}>
    <div className="px-10 py-8">
      <h1 className="m-0 text-xl font-semibold">{title}</h1>
      <p className="mt-2 max-w-prose text-muted">{description}</p>
      <p className="mt-4 text-muted">Coming soon.</p>
    </div>
  </PageFrame>
);
