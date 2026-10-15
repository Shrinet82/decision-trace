import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SourceDrawer } from '../components/SourceDrawer';
import type { Citation, GraphPath } from '../api/types';

describe('SourceDrawer Component', () => {
  const sampleCitation: Citation = {
    id: 'TICK-102',
    type: 'ticket',
    title: 'Redis session cluster operational maintenance and failover complexity',
  };

  const sampleGraphPath: GraphPath = {
    nodes: [
      {
        id: 'TICK-102',
        label: 'Ticket',
        properties: {
          ticket_id: 'TICK-102',
          title: 'Redis session cluster operational maintenance and failover complexity',
          date: '2026-05-12',
          rationale: 'High operational burden on redis master nodes under cluster failover.',
        },
      },
    ],
    edges: [],
    omitted_count: 0,
  };

  it('renders nothing when closed', () => {
    const { container } = render(
      <SourceDrawer
        isOpen={false}
        onClose={vi.fn()}
        citation={sampleCitation}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders source identifier, title, and metadata when open', () => {
    render(
      <SourceDrawer
        isOpen={true}
        onClose={vi.fn()}
        citation={sampleCitation}
        graphPath={sampleGraphPath}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByText('TICK-102').length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        'Redis session cluster operational maintenance and failover complexity'
      )
    ).toBeInTheDocument();
    expect(screen.getByText(/Recorded on 2026-05-12/)).toBeInTheDocument();
    expect(
      screen.getByText(
        'High operational burden on redis master nodes under cluster failover.'
      )
    ).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(
      <SourceDrawer
        isOpen={true}
        onClose={handleClose}
        citation={sampleCitation}
      />
    );

    const closeBtn = screen.getByLabelText('Close drawer');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    const handleClose = vi.fn();
    render(
      <SourceDrawer
        isOpen={true}
        onClose={handleClose}
        citation={sampleCitation}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
