import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusIcon } from '../components/StatusIcon';
import { statusSvgString } from '../utils/statusSvg';

describe('StatusIcon', () => {
  it('is decorative by default', () => {
    const { container } = render(<StatusIcon status="active" />);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('exposes the status name when labelled', () => {
    render(<StatusIcon status="stale" labelled />);
    expect(screen.getByRole('img', { name: 'Possibly stale' })).toBeInTheDocument();
  });

  it('draws the four distinct glyphs in the design colours', () => {
    expect(statusSvgString('active')).toContain('#2E9E6A');
    expect(statusSvgString('conflict')).toContain('#D9363E');
    expect(statusSvgString('stale')).toContain('stroke-dasharray');
    expect(statusSvgString('stale')).toContain('#C77D00');
    expect(statusSvgString('superseded')).toContain('#9A9DA4');
  });
});
