import React, { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { GitBranch } from 'lucide-react';
import { cancelJob, parseGithubEvent, resumeLatestJob, streamGithub } from '../../api/client';
import { invalidateGraphQueries } from '../../api/hooks';
import type { GithubEvent, GithubImportStats, GithubPhase, GithubProgress, IngestDiff } from '../../api/types';
import { useOrgAccess } from '../../org/useOrgAccess';
import { StatusIcon } from '../StatusIcon';
import { btnOutline, btnPrimary } from '../ui';
import { DiffCard } from './DiffCard';
import { useIngest } from './ingestContext';

const PHASES: { key: GithubPhase; label: string }[] = [
  { key: 'fetching', label: 'Fetching repository' },
  { key: 'extracting', label: 'Extracting systems and decisions' },
  { key: 'linking', label: 'Linking decisions' },
  { key: 'writing', label: 'Writing to FalkorDB' },
  { key: 'health', label: 'Recomputing health' },
];

const REPO_URL = /^(?:https?:\/\/)?(?:www\.)?github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:[/?#.].*)?$/;
const fieldClass =
  'h-[30px] w-full rounded-control border border-border bg-surface px-2 text-sm text-text placeholder:text-muted hover:border-[#D5D7DD] focus-visible:border-accent';

type Phase = 'form' | 'running' | 'done' | 'error';
type PhaseState = Record<GithubPhase, GithubProgress | undefined>;

/** Import ADRs, and decision-like PRs and issues, from a public GitHub repository. */
export const GithubPanel: React.FC = () => {
  const ingest = useIngest();
  const { isSample } = useOrgAccess();
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const [includePrs, setIncludePrs] = useState(true);
  const [phase, setPhase] = useState<Phase>('form');
  const [progress, setProgress] = useState<PhaseState>({ fetching: undefined, extracting: undefined, linking: undefined, writing: undefined, health: undefined });
  const [diff, setDiff] = useState<(IngestDiff & { import?: GithubImportStats }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const jobRef = useRef<string | null>(null);
  const setLatestDiff = ingest?.setLatestDiff;

  useEffect(() => () => abortRef.current?.abort(), []);

  const disabled = isSample;
  const valid = REPO_URL.test(url.trim());

  /** Run an import (or re-attach to one) and settle the panel on its result. */
  const track = async (run: (onEvent: (e: GithubEvent) => void, signal: AbortSignal) => Promise<unknown>) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let gotDiff = false;
    let message: string | null = null;
    try {
      const outcome = await run((event: GithubEvent) => {
        if (controller.signal.aborted) return;
        if (event.event === 'progress') setProgress((p) => ({ ...p, [event.data.phase]: event.data }));
        else if (event.event === 'diff') {
          gotDiff = true;
          setDiff(event.data);
          setLatestDiff?.(event.data);
          void invalidateGraphQueries(queryClient);
        } else message = event.data.message;
      }, controller.signal);
      if (controller.signal.aborted || outcome === false) return; // false: there was no job to re-attach to
      if (gotDiff) setPhase('done');
      else {
        setError(message ?? 'The import finished without a result. Try again.');
        setPhase('error');
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'The import failed.');
      setPhase('error');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  const begin = () => {
    setPhase('running');
    setProgress({ fetching: undefined, extracting: undefined, linking: undefined, writing: undefined, health: undefined });
    setDiff(null);
    setError(null);
  };

  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid || disabled) return;
    begin();
    await track((onEvent, signal) =>
      streamGithub(url.trim(), includePrs, onEvent, signal, (id) => {
        jobRef.current = id;
      })
    );
  };

  // A reloaded page finds an import that is still running (or just finished) and shows its progress
  useEffect(() => {
    if (disabled) return;
    void track((onEvent, signal) =>
      resumeLatestJob('github', parseGithubEvent, onEvent, signal, (id) => (jobRef.current = id), (job) => {
        begin();
        void job;
      })
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled]);

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (jobRef.current) void cancelJob(jobRef.current);
    setPhase('form');
  };

  if (phase === 'form') {
    return (
      <form onSubmit={start} className="flex flex-col gap-3" aria-label="GitHub repository">
        <p className="m-0 text-text-2">
          Import a public repository&rsquo;s architecture decision records. Status, &ldquo;Supersedes ADR-n&rdquo; lines,
          authors and dates map straight into the graph.
        </p>
        {disabled && (
          <p role="note" className="m-0 rounded-control border border-border bg-subtle px-3 py-2 text-text-2">
            GitHub import is available in organizations you create. Open the menu at the top of the sidebar and
            choose <strong>New organization</strong>; the sample organization stays as it is.
          </p>
        )}
        <div className="flex flex-col gap-1">
          <label htmlFor="github-url" className="text-xs font-medium text-text-2">
            Repository URL
          </label>
          <input
            id="github-url"
            type="url"
            inputMode="url"
            value={url}
            disabled={disabled}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            title={disabled ? 'Available in organizations you create' : undefined}
            className={fieldClass}
          />
        </div>
        <label className="flex items-start gap-2 text-text-2">
          <input
            type="checkbox"
            checked={includePrs}
            disabled={disabled}
            onChange={(e) => setIncludePrs(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 accent-[#4F5BD5]"
          />
          <span>
            Also read recent closed pull requests and issues that look like decisions
            <span className="block text-xs text-muted">Label or keyword: decision, RFC, ADR, proposal. Last 30 of each.</span>
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className={btnPrimary} disabled={!valid || disabled} title={disabled ? 'Available in organizations you create' : undefined}>
            <GitBranch size={14} aria-hidden="true" />
            Import
          </button>
          {url.trim() !== '' && !valid && !disabled && (
            <span role="status" className="text-xs text-muted">
              Use a URL like https://github.com/owner/repo.
            </span>
          )}
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <span className="font-medium text-text">{url.trim().replace(/^https?:\/\/(www\.)?github\.com\//, '')}</span>
        <span className="text-xs text-muted">GitHub import</span>
      </div>
      <section aria-labelledby="gh-steps-title" className="flex flex-col rounded-panel border border-divider">
        <div className="flex min-h-9 items-center justify-between gap-2 border-b border-divider px-3">
          <h3 id="gh-steps-title" className="m-0 text-sm font-medium">
            Steps
          </h3>
          {phase === 'running' && (
            <button type="button" className={btnOutline} onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
        <ol aria-label="Import steps" className="m-0 flex list-none flex-col p-0">
          {PHASES.map((p) => {
            const s = progress[p.key];
            const state = s ? s.status : phase === 'running' && PHASES.findIndex((x) => x.key === p.key) === PHASES.findIndex((x) => !progress[x.key] || progress[x.key]?.status === 'running') ? 'running' : 'pending';
            return (
              <li key={p.key} data-step={p.key} data-step-status={state} className="flex items-start gap-2.5 border-b border-row-divider px-3 py-2 last:border-b-0">
                <span className="mt-[3px] inline-flex shrink-0">
                  {state === 'done' ? (
                    <StatusIcon status="active" />
                  ) : (
                    <span aria-hidden="true" className={`inline-block h-3.5 w-3.5 rounded-full border-2 ${state === 'running' ? 'border-accent' : 'border-faint'}`} />
                  )}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className={state === 'pending' ? 'text-muted' : state === 'running' ? 'font-medium text-text' : 'text-text'}>
                    <span className="sr-only">{state}: </span>
                    {p.label}
                  </span>
                  {s?.detail && <span className="break-words text-xs text-muted">{s.detail}</span>}
                </span>
              </li>
            );
          })}
        </ol>
      </section>

      {phase === 'error' && (
        <div role="alert" className="flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg px-3 py-2.5">
          <span className="font-medium text-status-conflict-text">Import failed</span>
          <span className="text-text-2">{error}</span>
          <button type="button" className={btnOutline} onClick={() => setPhase('form')}>
            Back
          </button>
        </div>
      )}

      {phase === 'done' && diff && (
        <section aria-labelledby="gh-result-title" className="flex flex-col gap-2">
          <h3 id="gh-result-title" className="m-0 text-sm font-medium">
            Result
          </h3>
          {diff.import && (
            <p className="m-0 text-xs text-muted" data-testid="import-stats">
              {diff.import.adrs} ADRs · {diff.import.items_decisions} of {diff.import.items_considered} PRs/issues recorded a decision ·{' '}
              {diff.import.supersedes} supersedes · {diff.import.seconds}s · ~{diff.import.tokens_estimated.toLocaleString('en-US')} model tokens
            </p>
          )}
          <DiffCard diff={diff} onNavigate={ingest?.closeDrawer} />
          <div>
            <button type="button" className={btnOutline} onClick={() => setPhase('form')}>
              Import another repository
            </button>
          </div>
        </section>
      )}
    </div>
  );
};
