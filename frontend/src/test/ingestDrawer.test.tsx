import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { IngestEvent, IngestRequest } from '../api/types';
import { IngestProvider } from '../components/ingest/IngestProvider';
import { PageFrame } from '../components/PageFrame';
import { MOCK_INGEST_ALICE, MOCK_INGEST_KAFKA } from '../api/mocks';

/** A controllable fake stream: emits `before`, waits for `release()`, then emits `after`. */
const stream = vi.hoisted(() => ({
  before: [] as unknown[],
  after: [] as unknown[],
  release: () => {},
  requests: [] as unknown[],
}));

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return {
    ...actual,
    streamIngest: vi.fn(async (req: IngestRequest, onEvent: (e: IngestEvent) => void, signal?: AbortSignal) => {
      stream.requests.push(req);
      for (const e of stream.before) onEvent(e as IngestEvent);
      await new Promise<void>((resolve, reject) => {
        stream.release = resolve;
        signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      });
      for (const e of stream.after) onEvent(e as IngestEvent);
    }),
    resetIngest: vi.fn(async () => ({
      removed_nodes: 3,
      removed_edges: 8,
      restored_properties: 4,
      nodes: 146,
      edges: 392,
    })),
  };
});

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <IngestProvider>
          <Routes>
            <Route path="/" element={<PageFrame header={<span>Home</span>}>Home body</PageFrame>} />
            <Route path="/app/decisions/:code" element={<PageFrame header={<span>Decision</span>}>Decision body</PageFrame>} />
          </Routes>
        </IngestProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...utils, invalidate };
}

/** Splits a fixture so the stream pauses while `step` is running. */
function pauseAt(events: IngestEvent[], step: string) {
  const i = events.findIndex((e) => e.event === 'step' && e.data.step === step && e.data.status === 'running');
  stream.before = events.slice(0, i + 1);
  stream.after = events.slice(i + 1);
}

afterEach(() => {
  stream.requests = [];
});

describe('Add source drawer', () => {
  it('opens from the top bar, fills a preset, and returns focus on Escape', async () => {
    const user = userEvent.setup();
    renderApp();
    const trigger = screen.getByRole('button', { name: 'Add source' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveFocus();

    await user.click(within(dialog).getByRole('button', { name: 'Arch sync: standardise on Kafka' }));
    expect(within(dialog).getByLabelText('Type')).toHaveValue('meeting');
    expect(within(dialog).getByLabelText('Title')).toHaveValue('Architecture sync');
    expect(within(dialog).getByLabelText('Date')).toHaveValue('2026-10-16');
    expect(within(dialog).getByLabelText('Text')).toHaveValue(
      'Architecture sync, 2026-10-16. Attendees: Alice Vance, Bob Martin, Kevin Flynn. Decision: we standardise on Kafka for all event messaging across services. RabbitMQ is retired; Bob agreed to migrate remaining queues by Q1. Owner: Alice Vance.'
    );
    expect(within(dialog).getByLabelText(/Participants/)).toHaveValue('Alice Vance, Bob Martin, Kevin Flynn');
    const text = (within(dialog).getByLabelText('Text') as HTMLTextAreaElement).value;
    expect(dialog.querySelector('#ingest-text-count')).toHaveTextContent(`${text.length} / 5,000 characters`);

    await user.click(within(dialog).getByRole('button', { name: 'HR: Alice Vance leaves' }));
    expect(within(dialog).getByLabelText('Type')).toHaveValue('announcement');
    expect(within(dialog).getByLabelText('Title')).toHaveValue('People update: Alice Vance');
    expect(within(dialog).getByLabelText(/Participants/)).toHaveValue('');

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Add source' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('defaults the date to today and disables Run until the form is complete', async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    expect(within(dialog).getByLabelText('Date')).toHaveValue(
      new Date().toLocaleDateString('en-CA')
    );
    expect(within(dialog).getByRole('button', { name: 'Run' })).toBeDisabled();
  });

  it('shows running steps from streamed events, then the diff card with links', async () => {
    const user = userEvent.setup();
    pauseAt(MOCK_INGEST_KAFKA, 'linking');
    const { invalidate } = renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    await user.click(within(dialog).getByRole('button', { name: 'Arch sync: standardise on Kafka' }));
    await user.click(within(dialog).getByRole('button', { name: 'Run' }));

    expect(stream.requests[0]).toMatchObject({
      type: 'meeting',
      title: 'Architecture sync',
      participants: ['Alice Vance', 'Bob Martin', 'Kevin Flynn'],
    });

    const steps = await within(dialog).findByRole('list', { name: 'Ingest steps' });
    const items = within(steps).getAllByRole('listitem');
    expect(items).toHaveLength(7);
    expect(items.map((li) => li.getAttribute('data-step-status'))).toEqual([
      'done',
      'done',
      'done',
      'done',
      'running',
      'pending',
      'pending',
    ]);
    expect(items[4]).toHaveAttribute('aria-current', 'step');
    // Step details come straight from the (recorded) backend events
    const decisionsDone = MOCK_INGEST_KAFKA.find(
      (e) => e.event === 'step' && e.data.step === 'extracting_decisions' && e.data.status === 'done'
    );
    const detail = decisionsDone?.event === 'step' ? decisionsDone.data.detail ?? '' : '';
    expect(detail).not.toBe('');
    expect(items[1]).toHaveTextContent(detail);
    expect(within(dialog).getByRole('img', { name: /Graph changes/ })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

    stream.release();
    const result = await within(dialog).findByRole('region', { name: 'Ingest result' });
    expect(within(result).getByText('1 new decision · 2 status changes · conflict resolved')).toBeInTheDocument();
    const newDecisions = within(result).getByRole('region', { name: 'New decisions' });
    expect(within(newDecisions).getByRole('link', { name: 'DEC-18' })).toHaveAttribute('href', '/app/decisions/DEC-18');
    const statuses = within(result).getByRole('region', { name: 'Status changes' });
    expect(within(statuses).getByRole('link', { name: 'DEC-07' })).toHaveAttribute('href', '/app/decisions/DEC-07');
    expect(statuses).toHaveTextContent('DEC-07Contradicted→Superseded');
    const links = within(result).getByRole('region', { name: 'Links the judge made' });
    expect(links).toHaveTextContent(/DEC-18\s*supersedes\s*DEC-07/);
    expect(within(links).getByText(/retires RabbitMQ/)).toBeInTheDocument();
    expect(within(steps).getAllByRole('listitem').every((li) => li.getAttribute('data-step-status') === 'done')).toBe(
      true
    );

    // Pages refetch: every graph-derived query is invalidated
    expect(invalidate).toHaveBeenCalled();
    const predicate = invalidate.mock.calls[0][0]!.predicate!;
    const q = (key: string) => ({ queryKey: [key] }) as unknown as Parameters<typeof predicate>[0];
    for (const key of ['decisions', 'decision', 'systems', 'system', 'people', 'person', 'graph', 'changes']) {
      expect(predicate(q(key))).toBe(true);
    }
    expect(predicate(q('ask'))).toBe(false);

    // A diff link navigates and closes the drawer
    await user.click(within(newDecisions).getByRole('link', { name: 'DEC-18' }));
    expect(screen.queryByRole('dialog', { name: 'Add source' })).not.toBeInTheDocument();
    expect(screen.getByText('Decision body')).toBeInTheDocument();
  });

  it('lists people and orphaned systems for a departure', async () => {
    const user = userEvent.setup();
    stream.before = MOCK_INGEST_ALICE;
    stream.after = [];
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    await user.click(within(dialog).getByRole('button', { name: 'HR: Alice Vance leaves' }));
    await user.click(within(dialog).getByRole('button', { name: 'Run' }));
    stream.release();
    const people = await within(dialog).findByRole('region', { name: 'People' });
    expect(people).toHaveTextContent('Alice Vance: active → left company');
    const orphaned = within(dialog).getByRole('region', { name: 'Orphaned systems' });
    expect(within(orphaned).getByRole('link', { name: 'Kafka' })).toHaveAttribute('href', '/app/systems/Kafka');
    expect(orphaned).toHaveTextContent('Redis: owned → orphaned');
    // Every step completes; the steps with nothing to do report it in their detail
    const steps = within(dialog)
      .getAllByRole('listitem')
      .filter((li) => li.hasAttribute('data-step'));
    expect(steps.map((li) => li.getAttribute('data-step-status'))).toEqual(Array(7).fill('done'));
    expect(steps.find((li) => li.getAttribute('data-step') === 'linking')).toHaveTextContent('no links');
  });

  it('cancels a running ingest', async () => {
    const user = userEvent.setup();
    pauseAt(MOCK_INGEST_KAFKA, 'matching');
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    await user.click(within(dialog).getByRole('button', { name: 'Arch sync: standardise on Kafka' }));
    await user.click(within(dialog).getByRole('button', { name: 'Run' }));
    await user.click(await within(dialog).findByRole('button', { name: 'Cancel' }));
    expect(within(dialog).getByText('Ingest cancelled.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Title')).toHaveValue('Architecture sync');
  });

  it('shows an error with retry when the stream reports an error', async () => {
    const user = userEvent.setup();
    stream.before = [
      MOCK_INGEST_KAFKA[0],
      { event: 'error', data: { message: 'The extractor timed out.', step: 'reading' } },
    ];
    stream.after = [];
    renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    await user.click(within(dialog).getByRole('button', { name: 'Arch sync: standardise on Kafka' }));
    await user.click(within(dialog).getByRole('button', { name: 'Run' }));
    stream.release();
    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent('The extractor timed out.');
    expect(within(alert).getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('resets demo data after an inline confirmation', async () => {
    const user = userEvent.setup();
    const { invalidate } = renderApp();
    await user.click(screen.getByRole('button', { name: 'Add source' }));
    const dialog = screen.getByRole('dialog', { name: 'Add source' });
    await user.click(within(dialog).getByRole('button', { name: 'Reset demo data' }));
    expect(within(dialog).getByText('This removes all demo-ingested data.')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Reset' }));
    await waitFor(() =>
      expect(within(dialog).getByText(/Removed 3 nodes and 8 edges/)).toBeInTheDocument()
    );
    expect(invalidate).toHaveBeenCalled();
  });
});
