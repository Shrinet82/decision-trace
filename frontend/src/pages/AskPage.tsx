import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from '../router';
import { AlertCircle, ArrowUp, User } from 'lucide-react';
import { useDecisionDetail, useDecisions, useGraph } from '../api/hooks';
import { AnswerBody } from '../components/ask/AnswerBody';
import { AnswerSections } from '../components/ask/AnswerSections';
import { AskProperties } from '../components/ask/AskProperties';
import { EvidencePathCard } from '../components/ask/EvidencePathCard';
import { ExpertList } from '../components/ask/ExpertList';
import { HowIFound } from '../components/ask/HowIFound';
import { SourceCards } from '../components/ask/SourceCards';
import { PageFrame } from '../components/PageFrame';
import { StatusIcon } from '../components/StatusIcon';
import { btnOutline, btnPrimary } from '../components/ui';
import { SUGGESTED_QUESTIONS } from '../config/questions';
import { useAskRun } from '../hooks/useAskRun';
import type { AskResponse } from '../api/types';
import { isNotFoundAnswer } from '../utils/answer';
import { formatMs } from '../utils/format';
import { answerIsSubstantive, primaryNode, type AskRunState } from '../utils/askRun';
import { buildEvidencePath } from '../utils/evidence';
import { decisionHref } from '../utils/links';
import { withBase } from '../org/orgState';
import {
  buildGraphIndex,
  healthToStatus,
  STATUS_LABEL,
  type GraphIndex,
  type StatusKind,
} from '../utils/model';

const VERDICT: Record<StatusKind, string> = {
  active: 'Still valid',
  conflict: 'Conflicting decisions',
  stale: STATUS_LABEL.stale,
  superseded: STATUS_LABEL.superseded,
};

const AnswerSkeleton: React.FC = () => (
  <div role="status" aria-label="Searching the Company Brain" className="flex flex-col gap-3">
    <div className="skeleton h-[22px] w-28" />
    <div className="skeleton h-4 w-full" />
    <div className="skeleton h-4 w-11/12" />
    <div className="skeleton h-4 w-3/4" />
  </div>
);

/** What a run currently shows: the answer text, the structured results, and the primary decision. */
function viewOf(run: AskRunState | null) {
  const result = run?.result ?? null;
  const notFound = result ? isNotFoundAnswer(result.answer) : false;
  const streaming = run && !result && answerIsSubstantive(run.answer) ? run.answer : null;
  return {
    result,
    notFound,
    answer: result && !notFound ? result.answer : streaming,
    sections: notFound ? [] : (result?.sections ?? run?.path?.sections ?? []),
    experts: notFound ? [] : (result?.experts ?? run?.path?.experts ?? []),
    main: notFound ? undefined : primaryNode(run),
    graphPath: result?.graph_path ?? run?.path?.graph_path,
    busy: Boolean(run && !result && !run.error),
  };
}

interface TurnProps {
  question: string;
  turnKey: string;
  index: GraphIndex | undefined;
  decisionCount: number | undefined;
  statusById: Map<string, StatusKind>;
}

const Turn: React.FC<TurnProps> = ({ question, turnKey, index, decisionCount, statusById }) => {
  const { run, retry } = useAskRun(question);
  const view = viewOf(run);
  const { main } = view;
  const detail = useDecisionDetail(main?.id);

  const scrollTo = (anchorId: string) => {
    const el = document.getElementById(anchorId);
    el?.scrollIntoView?.({ block: 'center' });
    el?.focus({ preventScroll: true });
  };

  const verdictStatus = detail.data ? healthToStatus(detail.data.health) : null;
  const subject = run?.entities.find((e) => e.label === 'System')?.name;
  const evidence =
    main && view.graphPath
      ? buildEvidencePath({ graph_path: view.graphPath } as AskResponse, main.id)
      : null;

  return (
    <>
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-hover text-text-2"
        >
          <User className="h-3.5 w-3.5" />
        </span>
        <p className="m-0 pt-0.5 text-lg font-medium">{question}</p>
      </div>

      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-control bg-accent text-[10px] font-semibold text-white"
        >
          DT
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {/* On narrow screens the trace sits above the answer; on wide screens it is in the side panel */}
          {run && (
            <details className="rounded-panel border border-divider bg-subtle min-[900px]:hidden">
              <summary className="flex cursor-pointer items-center justify-between gap-2 px-3 py-2 text-sm font-medium">
                How I found this
                <span className="text-xs font-normal text-muted">
                  {run.totalMs !== null ? formatMs(run.totalMs) : (run.steps.find((s) => s.status === 'running')?.label ?? '')}
                </span>
              </summary>
              <div className="border-t border-divider bg-surface px-3 py-2">
                <HowIFound run={run} headingLevel="h3" showTitle={false} />
              </div>
            </details>
          )}

          {run?.error && (
            <div
              role="alert"
              className="flex flex-col gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg p-3"
            >
              <div className="flex items-center gap-2 font-medium text-status-conflict-text">
                <AlertCircle className="h-4 w-4" aria-hidden="true" />
                Search failed
              </div>
              <p className="m-0 text-text-2">{run.error}</p>
              <div>
                <button type="button" onClick={retry} className={btnOutline}>
                  Retry
                </button>
              </div>
            </div>
          )}

          {!run?.error && !view.answer && !view.notFound && <AnswerSkeleton />}

          {view.notFound && (
            <div role="status" className="flex flex-col gap-1 rounded-panel border border-divider bg-subtle px-4 py-5">
              <h2 className="m-0 text-lg font-semibold">No decision found</h2>
              <p className="m-0 text-muted">
                Nothing in the indexed tickets, notes, and records answers this question.
              </p>
            </div>
          )}

          {main && (
            <div className="flex flex-wrap items-center gap-2">
              {verdictStatus && (
                <span className="inline-flex h-[22px] items-center gap-1.5 rounded-chip border border-border px-2 text-xs font-medium">
                  <StatusIcon status={verdictStatus} size={12} />
                  {VERDICT[verdictStatus]}
                </span>
              )}
              <Link
                to={decisionHref(String(main.properties.decision_code ?? main.id))}
                title={String(main.properties.title ?? '')}
                className="inline-flex h-[22px] max-w-full items-center gap-1 truncate rounded-chip border border-border px-2 text-xs text-accent hover:bg-subtle"
              >
                {String(main.properties.decision_code ?? 'Decision')}
                <span className="truncate text-text-2">· {String(main.properties.title ?? '')}</span>
              </Link>
              {decisionCount !== undefined && (
                <span className="text-xs text-muted">Health checked across {decisionCount} decisions</span>
              )}
            </div>
          )}

          {view.answer && (
            <div aria-busy={view.busy || undefined}>
              <AnswerBody
                answer={view.answer}
                citations={view.result?.citations ?? []}
                turnKey={turnKey}
                onCite={scrollTo}
              />
            </div>
          )}

          {view.experts.length > 0 && <ExpertList experts={view.experts} subject={subject} />}

          {view.sections.length > 0 && (
            <AnswerSections
              sections={view.sections}
              label={run?.intent === 'impact' ? `Impact of changing ${subject ?? 'this system'}` : 'Health results'}
            />
          )}

          {main && evidence && evidence.rows.length > 0 && (
            <EvidencePathCard path={evidence} statusOf={(id) => statusById.get(id) ?? 'active'} animate />
          )}

          {view.result && view.result.citations.length > 0 && !view.notFound && (
            <SourceCards citations={view.result.citations} turnKey={turnKey} index={index} />
          )}
        </div>
      </div>
    </>
  );
};

export const AskPage: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [input, setInput] = useState('');
  const [turns, setTurns] = useState<string[]>([]);
  const composerRef = useRef<HTMLInputElement>(null);

  const graphQuery = useGraph();
  const decisionsQuery = useDecisions();
  const index = useMemo(
    () => (graphQuery.data ? buildGraphIndex(graphQuery.data) : undefined),
    [graphQuery.data]
  );
  const statusById = useMemo(() => {
    const map = new Map<string, StatusKind>();
    for (const d of decisionsQuery.data ?? []) map.set(d.id, healthToStatus(d.health));
    return map;
  }, [decisionsQuery.data]);

  const submit = (raw: string) => {
    const q = raw.trim();
    if (q.length < 2) return;
    setTurns((prev) => [...prev, q]);
    setInput('');
  };

  // Deep link: /ask?q=... asks once, then clears the parameter.
  const seeded = useRef<string | null>(null);
  useEffect(() => {
    const q = params.get('q');
    if (q && seeded.current !== q) {
      seeded.current = q;
      submit(q);
      const next = new URLSearchParams(params);
      next.delete('q');
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const lastQuestion = turns.length > 0 ? turns[turns.length - 1] : null;
  const { run: lastRun } = useAskRun(lastQuestion);
  const lastView = viewOf(lastRun);
  const lastMain = lastView.main;
  const lastDetail = useDecisionDetail(lastMain?.id);

  useEffect(() => {
    if (turns.length > 0) {
      window.scrollTo?.({ top: document.body.scrollHeight, behavior: 'smooth' });
    }
  }, [turns.length]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  const copyLink = async () => {
    if (!lastQuestion) return;
    const url = `${window.location.origin}${withBase('/ask')}?q=${encodeURIComponent(lastQuestion)}`;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      // Clipboard can be blocked; the link is still visible in the address bar flow.
    }
  };

  const header = (
    <>
      <span>Ask</span>
      {lastQuestion && (
        <>
          <span aria-hidden="true">/</span>
          <span className="truncate font-medium text-text">{lastQuestion}</span>
        </>
      )}
    </>
  );

  const actions = lastQuestion ? (
    <>
      <button type="button" onClick={copyLink} className={btnOutline}>
        Copy link
      </button>
      <button
        type="button"
        disabled={!lastMain}
        onClick={() => lastMain && navigate(`/explore?node=${encodeURIComponent(lastMain.id)}`)}
        className={btnOutline}
      >
        Open in graph
      </button>
    </>
  ) : undefined;

  const panel = (
    <AskProperties
      before={lastRun ? <div className="max-[899px]:hidden"><HowIFound run={lastRun} /></div> : undefined}
      detail={lastDetail.data}
      loading={Boolean(lastMain) && lastDetail.isLoading}
      emptyText={
        lastRun?.result && !lastMain
          ? 'This answer is not about a single decision, so there are no decision properties to show.'
          : undefined
      }
    />
  );

  return (
    <PageFrame header={header} actions={actions} panel={panel}>
      <div className="mx-auto flex min-h-[calc(100vh-45px)] max-w-[820px] flex-col gap-7 px-5 pt-8 min-[900px]:px-10">
        <h1 className={turns.length > 0 ? 'sr-only' : 'm-0 text-[20px] font-semibold'}>Ask</h1>

        {turns.length === 0 && (
          <p className="m-0 max-w-prose text-muted">
            Ask why a decision was made, what a change would affect, who knows a system, or which
            decisions conflict. Every answer shows the graph steps behind it and cites its sources.
          </p>
        )}

        {turns.map((q, i) => (
          <Turn
            key={`${i}-${q}`}
            question={q}
            turnKey={String(i)}
            index={index}
            decisionCount={decisionsQuery.data?.length}
            statusById={statusById}
          />
        ))}

        <form onSubmit={onSubmit} className="sticky bottom-0 z-10 mt-auto flex flex-col gap-2.5 bg-surface pb-4 pt-2">
          <div className="flex items-center gap-2 rounded-[10px] border border-border bg-surface py-2 pl-3.5 pr-2 shadow-composer">
            <label htmlFor="question-input" className="sr-only">
              {turns.length > 0 ? 'Ask a follow-up' : 'Ask a question'}
            </label>
            <input
              ref={composerRef}
              id="question-input"
              type="text"
              value={input}
              maxLength={500}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                turns.length > 0
                  ? 'Ask a follow-up…'
                  : 'Ask why a decision was made, who owns a system, or what replaced something'
              }
              className="h-7 min-w-0 flex-1 border-0 bg-transparent text-base text-text outline-none placeholder:text-muted"
            />
            <button
              type="submit"
              id="ask-submit-button"
              disabled={lastView.busy || input.trim().length < 2}
              className={btnPrimary}
            >
              <ArrowUp className="h-3.5 w-3.5 sm:hidden" aria-hidden="true" />
              <span className="max-sm:sr-only">Ask</span>
            </button>
          </div>
          {turns.length === 0 && (
            <div className="flex flex-col items-start gap-1.5">
              <span id="suggested-label" className="text-xs font-medium text-muted">
                Suggested questions
              </span>
              <ul aria-labelledby="suggested-label" className="m-0 flex list-none flex-wrap gap-2 p-0">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => submit(q)}
                      className="rounded-chip border border-border bg-surface px-3 py-1 text-left text-sm text-text-2 transition-colors hover:bg-subtle"
                    >
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </form>
      </div>
    </PageFrame>
  );
};
