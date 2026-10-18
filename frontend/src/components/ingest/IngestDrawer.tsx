import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { RotateCcw } from 'lucide-react';
import { resetIngest, streamIngest } from '../../api/client';
import { invalidateGraphQueries, useDemoStatus } from '../../api/hooks';
import type { IngestRequest, IngestSourceType, ResetResult } from '../../api/types';
import { resetCountdownText } from '../../utils/demo';
import { emptyForm, MAX_TEXT, PRESETS, toIngestRequest, TYPE_LABEL, type IngestForm } from './ingestForm';
import { formatLongDate } from '../../utils/format';
import { applyIngestEvent, initialRun, miniGraphElements, type RunState } from '../../utils/ingestRun';
import { CytoscapeGraph } from '../CytoscapeGraph';
import { Drawer } from '../Drawer';
import { FEATURES } from '../../config/features';
import { useOrgSlug } from '../../org/OrgContext';
import { UploadPanel } from './UploadPanel';
import { btnOutline, btnPrimary } from '../ui';
import { DiffCard } from './DiffCard';
import { useIngest, type IngestTab } from './ingestContext';
import { StepList } from './StepList';

const fieldClass =
  'w-full rounded-control border border-border bg-surface px-2 text-sm text-text placeholder:text-muted hover:border-[#D5D7DD] focus-visible:border-accent';
const labelClass = 'text-xs font-medium text-text-2';

type Phase = 'form' | 'running' | 'done' | 'error';

const ResetCountdown: React.FC = () => {
  const ingest = useIngest();
  const status = useDemoStatus(ingest?.drawerOpen ?? true);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <span data-testid="reset-countdown" className="text-xs text-muted">
      {resetCountdownText(status.data, now)}
    </span>
  );
};

const ResetControl: React.FC<{ disabled: boolean; onReset: () => void }> = ({ disabled, onReset }) => {
  const queryClient = useQueryClient();
  const ingest = useIngest();
  const [state, setState] = useState<
    | { kind: 'idle' }
    | { kind: 'confirm' }
    | { kind: 'busy' }
    | { kind: 'done'; result: ResetResult }
    | { kind: 'error'; message: string }
  >({ kind: 'idle' });

  const confirm = async () => {
    setState({ kind: 'busy' });
    try {
      const result = await resetIngest();
      ingest?.setLatestDiff(null);
      onReset();
      void invalidateGraphQueries(queryClient);
      setState({ kind: 'done', result });
    } catch (err) {
      setState({ kind: 'error', message: err instanceof Error ? err.message : 'Reset failed.' });
    }
  };

  if (state.kind === 'confirm' || state.kind === 'busy') {
    return (
      <div className="flex flex-col gap-2">
        <p className="m-0 text-text-2">This removes all demo-ingested data.</p>
        <div className="flex gap-1.5">
          <button
            type="button"
            className={`${btnOutline} border-status-conflict-border text-status-conflict-text`}
            onClick={confirm}
            disabled={state.kind === 'busy'}
          >
            {state.kind === 'busy' ? 'Resetting…' : 'Reset'}
          </button>
          <button
            type="button"
            className={btnOutline}
            onClick={() => setState({ kind: 'idle' })}
            disabled={state.kind === 'busy'}
          >
            Keep data
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ResetCountdown />
        <button
          type="button"
          className={btnOutline}
          onClick={() => setState({ kind: 'confirm' })}
          disabled={disabled}
        >
          <RotateCcw size={13} aria-hidden="true" />
          Reset demo data
        </button>
      </div>
      <div role="status" className="text-xs">
        {state.kind === 'done' && (
          <span className="text-text-2">
            Reset complete. Removed {state.result.removed_nodes} nodes and {state.result.removed_edges} edges,
            restored {state.result.restored_properties} properties. The graph now has {state.result.nodes} nodes and{' '}
            {state.result.edges} edges.
          </span>
        )}
      </div>
      {state.kind === 'error' && (
        <p role="alert" className="m-0 text-xs text-status-conflict-text">
          {state.message}
        </p>
      )}
    </div>
  );
};

export const IngestDrawer: React.FC = () => {
  const ingest = useIngest();
  const orgSlug = useOrgSlug();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<IngestForm>(emptyForm);
  const [phase, setPhase] = useState<Phase>('form');
  const [run, setRun] = useState<RunState>(initialRun);
  const [request, setRequest] = useState<IngestRequest | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const setLatestDiff = ingest?.setLatestDiff;

  useEffect(() => () => abortRef.current?.abort(), []);

  const start = useCallback(
    async (req: IngestRequest) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setRequest(req);
      setRun(initialRun());
      setErrorMessage(null);
      setNotice(null);
      setPhase('running');
      const outcome: { diff: boolean; error: string | null } = { diff: false, error: null };
      try {
        await streamIngest(
          req,
          (event) => {
            if (controller.signal.aborted) return;
            setRun((s) => applyIngestEvent(s, event));
            if (event.event === 'diff') {
              outcome.diff = true;
              setLatestDiff?.(event.data);
              void invalidateGraphQueries(queryClient);
            } else if (event.event === 'error') {
              outcome.error = event.data.message;
            }
          },
          controller.signal
        );
        if (controller.signal.aborted) return;
        if (outcome.error) {
          setErrorMessage(outcome.error);
          setPhase('error');
        } else if (outcome.diff) {
          setPhase('done');
        } else {
          setErrorMessage('The ingest finished without a result. Try again.');
          setPhase('error');
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        setErrorMessage(err instanceof Error ? err.message : 'Ingest failed.');
        setPhase('error');
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [queryClient, setLatestDiff]
  );

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase('form');
    setNotice('Ingest cancelled.');
  };

  const newSource = () => {
    setPhase('form');
    setRun(initialRun());
    setNotice(null);
  };

  const elements = useMemo(() => miniGraphElements(run.graph), [run.graph]);
  const valid =
    form.title.trim().length > 0 &&
    form.text.trim().length > 0 &&
    form.text.length <= MAX_TEXT &&
    /^\d{4}-\d{2}-\d{2}$/.test(form.date);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (valid) void start(toIngestRequest(form));
  };

  const set = <K extends keyof IngestForm>(key: K, value: IngestForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const running = run.steps.find((s) => s.status === 'running');
  const added = run.graph.nodes.filter((n) => n.change === 'added').length;
  const changed = run.graph.nodes.filter((n) => n.change === 'changed').length;

  if (!ingest) return null;

  const tabs: { key: IngestTab; label: string }[] = [
    { key: 'paste', label: 'Paste text' },
    ...(FEATURES.upload ? [{ key: 'files' as const, label: 'Upload files' }] : []),
  ];

  return (
    <Drawer
      open={ingest.drawerOpen}
      onClose={ingest.closeDrawer}
      title="Add source"
      titleId="ingest-drawer-title"
      keepMounted
      footer={orgSlug ? undefined : <ResetControl disabled={phase === 'running'} onReset={newSource} />}
    >
      <div className="flex flex-col gap-4 p-4">
        {tabs.length > 1 && (
          <div role="tablist" aria-label="How to add a source" className="flex gap-1 border-b border-divider">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`ingest-tab-${t.key}`}
                aria-selected={ingest.tab === t.key}
                aria-controls={`ingest-panel-${t.key}`}
                onClick={() => ingest.setTab(t.key)}
                className={`-mb-px h-8 border-b-2 px-3 text-sm ${
                  ingest.tab === t.key ? 'border-accent font-medium text-text' : 'border-transparent text-text-2 hover:text-text'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        )}
        <div
          role={tabs.length > 1 ? 'tabpanel' : undefined}
          id="ingest-panel-paste"
          aria-labelledby={tabs.length > 1 ? 'ingest-tab-paste' : undefined}
          hidden={tabs.length > 1 && ingest.tab !== 'paste'}
          className="flex flex-col gap-4"
        >
        {phase === 'form' ? (
          <form onSubmit={submit} className="flex flex-col gap-3" aria-label="Source">
            <p className="m-0 text-text-2">
              Paste meeting notes, a ticket or an announcement. Decisions and people are extracted, linked to
              the graph, and decision health is recomputed.
            </p>
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted" id="ingest-presets-label">
                Examples
              </span>
              <div role="group" aria-labelledby="ingest-presets-label" className="flex flex-wrap gap-1.5">
                {PRESETS.map((p) => (
                  <button key={p.label} type="button" className={btnOutline} onClick={() => setForm({ ...p.form })}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 min-[400px]:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label htmlFor="ingest-type" className={labelClass}>
                  Type
                </label>
                <select
                  id="ingest-type"
                  value={form.type}
                  onChange={(e) => set('type', e.target.value as IngestSourceType)}
                  className={`${fieldClass} h-[30px]`}
                >
                  {(Object.keys(TYPE_LABEL) as IngestSourceType[]).map((t) => (
                    <option key={t} value={t}>
                      {TYPE_LABEL[t]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="ingest-date" className={labelClass}>
                  Date
                </label>
                <input
                  id="ingest-date"
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => set('date', e.target.value)}
                  className={`${fieldClass} h-[30px]`}
                />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="ingest-title" className={labelClass}>
                Title
              </label>
              <input
                id="ingest-title"
                type="text"
                required
                maxLength={200}
                value={form.title}
                onChange={(e) => set('title', e.target.value)}
                placeholder="Architecture sync"
                className={`${fieldClass} h-[30px]`}
              />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline justify-between">
                <label htmlFor="ingest-text" className={labelClass}>
                  Text
                </label>
                <span
                  id="ingest-text-count"
                  className={`text-xs tabular-nums ${form.text.length > MAX_TEXT ? 'text-status-conflict-text' : 'text-muted'}`}
                >
                  {form.text.length.toLocaleString('en-US')} / {MAX_TEXT.toLocaleString('en-US')}
                  <span className="sr-only"> characters</span>
                </span>
              </div>
              <textarea
                id="ingest-text"
                required
                rows={8}
                maxLength={MAX_TEXT}
                value={form.text}
                onChange={(e) => set('text', e.target.value)}
                aria-describedby="ingest-text-count"
                placeholder="Meeting notes, ticket body or announcement"
                className={`${fieldClass} resize-y py-1.5 leading-[1.5]`}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="ingest-participants" className={labelClass}>
                Participants <span className="font-normal text-muted">(optional, comma separated)</span>
              </label>
              <input
                id="ingest-participants"
                type="text"
                value={form.participants}
                onChange={(e) => set('participants', e.target.value)}
                placeholder="Alice Vance, Bob Martin"
                className={`${fieldClass} h-[30px]`}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className={btnPrimary} disabled={!valid}>
                Run
              </button>
              {!valid && <span className="text-xs text-muted">Title, date and text are required.</span>}
            </div>
            {notice && (
              <p role="status" className="m-0 text-xs text-muted">
                {notice}
              </p>
            )}
          </form>
        ) : (
          <>
            {request && (
              <div className="flex flex-col gap-0.5">
                <span className="font-medium text-text">{request.title}</span>
                <span className="text-xs text-muted">
                  {TYPE_LABEL[request.type]} · {formatLongDate(request.date) || request.date}
                  {request.participants ? ` · ${request.participants.length} participants` : ''}
                </span>
              </div>
            )}

            <section aria-labelledby="ingest-steps-title" className="flex flex-col rounded-panel border border-divider">
              <div className="flex min-h-9 items-center justify-between gap-2 border-b border-divider px-3">
                <h3 id="ingest-steps-title" className="m-0 text-sm font-medium">
                  Steps
                </h3>
                {phase === 'running' && (
                  <button type="button" className={btnOutline} onClick={cancel}>
                    Cancel
                  </button>
                )}
              </div>
              <StepList steps={run.steps} />
              <p role="status" className="sr-only">
                {phase === 'running' && running ? `${running.label}…` : ''}
                {phase === 'done' ? 'Ingest complete.' : ''}
              </p>
            </section>

            {/* Mounted only while visible so the layout is computed at the real size */}
            {ingest.drawerOpen && run.graph.nodes.length > 0 && (
              <section aria-labelledby="ingest-graph-title" className="flex flex-col rounded-panel border border-divider">
                <div className="flex min-h-9 items-center justify-between gap-2 border-b border-divider px-3">
                  <h3 id="ingest-graph-title" className="m-0 text-sm font-medium">
                    Graph changes
                  </h3>
                  <span className="text-xs text-muted">
                    {added} added · {changed} changed
                  </span>
                </div>
                <CytoscapeGraph
                  elements={elements}
                  focusId={null}
                  layout="lr"
                  className="h-[220px]"
                  selectedId={null}
                  onSelect={() => undefined}
                  fitSignal={0}
                  ariaLabel={`Graph changes: ${added} nodes added, ${changed} changed, ${run.graph.nodes.length - added - changed} existing nodes for context.`}
                />
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-divider px-3 py-2 text-xs text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px] border-2 border-accent" /> added
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px] border-2 border-status-stale" /> changed
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-[3px] border border-border" /> existing
                  </span>
                </div>
                <ul aria-label="Graph change list" className="sr-only">
                  {run.graph.nodes.map((n) => (
                    <li key={n.id}>
                      {n.label}: {n.decision_code ? `${n.decision_code} ` : ''}
                      {n.name} ({n.change === 'context' ? 'existing' : n.change})
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {phase === 'error' && (
              <div
                role="alert"
                className="flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg px-3 py-2.5"
              >
                <span className="font-medium text-status-conflict-text">Ingest failed</span>
                <span className="text-text-2">{errorMessage}</span>
                <div className="flex gap-1.5">
                  {request && (
                    <button type="button" className={btnOutline} onClick={() => void start(request)}>
                      Try again
                    </button>
                  )}
                  <button type="button" className={btnOutline} onClick={newSource}>
                    Edit source
                  </button>
                </div>
              </div>
            )}

            {phase === 'done' && run.diff && (
              <section aria-labelledby="ingest-result-title" className="flex flex-col gap-2">
                <h3 id="ingest-result-title" className="m-0 text-sm font-medium">
                  Result
                </h3>
                <DiffCard diff={run.diff} onNavigate={ingest.closeDrawer} />
                <div>
                  <button type="button" className={btnOutline} onClick={newSource}>
                    Add another source
                  </button>
                </div>
              </section>
            )}
          </>
        )}
        </div>
        {FEATURES.upload && (
          <div role="tabpanel" id="ingest-panel-files" aria-labelledby="ingest-tab-files" hidden={ingest.tab !== 'files'}>
            <UploadPanel />
          </div>
        )}
      </div>
    </Drawer>
  );
};
