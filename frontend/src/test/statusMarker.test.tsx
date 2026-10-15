import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusMarker } from '../components/StatusMarker';

describe('StatusMarker Component', () => {
  it('renders Active status with label and accessible role', () => {
    render(<StatusMarker health="active" healthReason="Healthy and adopted" />);
    const marker = screen.getByRole('status');
    expect(marker).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(marker).toHaveAttribute('aria-label', 'Active: Healthy and adopted');
    expect(marker).toHaveAttribute('title', 'Active: Healthy and adopted');
  });

  it('renders Superseded status with hollow/strike styling', () => {
    render(<StatusMarker health="superseded" healthReason="Replaced by Keycloak" />);
    const marker = screen.getByRole('status');
    expect(marker).toBeInTheDocument();
    expect(screen.getByText('Superseded')).toBeInTheDocument();
    expect(marker).toHaveAttribute('aria-label', 'Superseded: Replaced by Keycloak');
  });

  it('renders Contradicted status with split styling', () => {
    render(<StatusMarker health="contradicted" healthReason="Direct conflict with Kafka" />);
    const marker = screen.getByRole('status');
    expect(marker).toBeInTheDocument();
    expect(screen.getByText('Contradicted')).toBeInTheDocument();
    expect(marker).toHaveAttribute('aria-label', 'Contradicted: Direct conflict with Kafka');
  });

  it('renders Possibly stale status with dashed outline', () => {
    render(<StatusMarker health="possibly_stale" healthReason="Over 90 days since update" />);
    const marker = screen.getByRole('status');
    expect(marker).toBeInTheDocument();
    expect(screen.getByText('Possibly stale')).toBeInTheDocument();
    expect(marker).toHaveAttribute('aria-label', 'Possibly stale: Over 90 days since update');
  });

  it('can hide the text label when showLabel is false', () => {
    render(<StatusMarker health="active" showLabel={false} healthReason="Active" />);
    const marker = screen.getByRole('status');
    expect(marker).toBeInTheDocument();
    expect(screen.queryByText('Active')).not.toBeInTheDocument();
    expect(marker).toHaveAttribute('aria-label', 'Active: Active');
  });
});
