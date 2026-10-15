import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Users,
  FileText,
  AlertCircle,
  RotateCcw,
  History,
} from 'lucide-react';
import { askQuestion, ApiError } from '../api/client';
import type { AskResponse, Citation } from '../api/types';
import { StatusMarker } from '../components/StatusMarker';
import { CytoscapeGraph } from '../components/CytoscapeGraph';
import { SourceDrawer } from '../components/SourceDrawer';
import { getSystemLine } from '../config/lines';

const EXAMPLE_QUESTIONS = [
  'Why did we choose Kafka over RabbitMQ?',
  'Who owns Elasticsearch?',
  'What replaced Redis for session storage?',
  'Who decided to adopt Prometheus?',
  'Why did we choose Vault for secret management?',
];

export const AskPage: React.FC = () => {
  const [questionInput, setQuestionInput] = useState('');
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(null);
  const [recentQueries, setRecentQueries] = useState<string[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // TanStack Query for answering questions
  const {
    data,
    error,
    isLoading,
    isFetching,
    refetch,
  } = useQuery<AskResponse, ApiError>({
    queryKey: ['ask', submittedQuestion],
    queryFn: () => askQuestion({ question: submittedQuestion! }),
    enabled: Boolean(submittedQuestion && submittedQuestion.trim().length >= 2),
    staleTime: 1000 * 60 * 5, // 5 minutes cache
    retry: 1,
  });

  const handleAsk = (q: string) => {
    const trimmed = q.trim();
    if (trimmed.length < 2) return;

    setQuestionInput(trimmed);
    setSubmittedQuestion(trimmed);
    setRecentQueries((prev) => {
      const filtered = prev.filter((item) => item !== trimmed);
      return [trimmed, ...filtered].slice(0, 5);
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAsk(questionInput);
  };

  const handleOpenSource = (citation: Citation) => {
    setSelectedCitation(citation);
    setIsDrawerOpen(true);
  };

  // Inspect if the answer represents a "not found" state
  const isNotFound =
    data &&
    ((data.citations?.length ?? 0) === 0 ||
      data.answer.toLowerCase().includes('not found in the company brain') ||
      data.answer.toLowerCase().includes('the answer is not found'));

  // Extract decision nodes from graph_path for summary cards
  const decisionNodes =
    data?.graph_path?.nodes?.filter((n) => n.label === 'Decision') || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-text tracking-tight">
          Ask
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Query why decisions were made, who owns a system, or what replaced something with grounded evidence.
        </p>
      </div>

      {/* Question Form */}
      <div className="bg-surface border border-border rounded-panel p-4 space-y-3">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted"
              aria-hidden="true"
            />
            <input
              type="text"
              id="question-input"
              value={questionInput}
              onChange={(e) => setQuestionInput(e.target.value)}
              placeholder="Ask why a decision was made, who owns a system, or what replaced something"
              disabled={isLoading || isFetching}
              className="w-full pl-9 pr-3 py-2 text-sm bg-surface-subtle border border-border rounded-control text-text placeholder:text-text-muted focus-visible:outline-focus disabled:opacity-60"
            />
          </div>

          <button
            type="submit"
            id="ask-submit-button"
            disabled={isLoading || isFetching || questionInput.trim().length < 2}
            className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-sm font-semibold rounded-control transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-focus"
          >
            {isLoading || isFetching ? 'Searching…' : 'Ask'}
          </button>
        </form>

        {/* Example Questions */}
        <div className="space-y-1.5 pt-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-muted block">
            Example questions:
          </span>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map((example, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleAsk(example)}
                disabled={isLoading || isFetching}
                className="px-2.5 py-1 text-xs rounded-control border border-border bg-surface-subtle hover:bg-surface text-text hover:border-primary transition-colors text-left focus-visible:outline-focus disabled:opacity-60"
              >
                {example}
              </button>
            ))}
          </div>
        </div>

        {/* In-session recent queries history */}
        {recentQueries.length > 0 && (
          <div className="flex items-center gap-2 pt-2 border-t border-border text-xs text-text-muted">
            <History className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            <span className="font-medium text-text">Recent:</span>
            <div className="flex flex-wrap gap-1.5 overflow-x-auto">
              {recentQueries.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleAsk(item)}
                  className="hover:text-primary hover:underline truncate max-w-xs focus-visible:outline-focus"
                >
                  {item}
                  {idx < recentQueries.length - 1 && ' ·'}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Loading Skeleton State */}
      {(isLoading || isFetching) && (
        <div
          className="grid grid-cols-1 lg:grid-cols-12 gap-6"
          role="status"
          aria-live="polite"
          aria-label="Searching knowledge graph"
        >
          {/* Answer column skeleton (~60%) */}
          <div className="lg:col-span-7 space-y-4">
            <div className="p-5 bg-surface border border-border rounded-panel space-y-3 animate-pulse">
              <div className="h-4 bg-surface-subtle rounded w-1/4" />
              <div className="h-4 bg-surface-subtle rounded w-full" />
              <div className="h-4 bg-surface-subtle rounded w-5/6" />
              <div className="h-4 bg-surface-subtle rounded w-3/4" />
            </div>

            <div className="p-5 bg-surface border border-border rounded-panel space-y-3 animate-pulse">
              <div className="h-4 bg-surface-subtle rounded w-1/3" />
              <div className="h-12 bg-surface-subtle rounded w-full" />
              <div className="h-12 bg-surface-subtle rounded w-full" />
            </div>
          </div>

          {/* Evidence column skeleton (~40%) */}
          <div className="lg:col-span-5">
            <div className="h-[420px] bg-surface border border-border rounded-panel p-4 animate-pulse flex flex-col justify-between">
              <div className="h-6 bg-surface-subtle rounded w-1/3" />
              <div className="h-48 bg-surface-subtle rounded w-full" />
              <div className="h-8 bg-surface-subtle rounded w-full" />
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && !isFetching && (
        <div
          className="p-5 bg-surface border border-danger/40 rounded-panel text-sm text-text space-y-3"
          role="alert"
        >
          <div className="flex items-center gap-2 text-danger font-semibold">
            <AlertCircle className="w-5 h-5 shrink-0" aria-hidden="true" />
            <span>Search query failed</span>
          </div>
          <p className="text-text-muted">
            {error.message || 'An error occurred while querying the Company Brain.'}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-control text-xs font-semibold bg-surface border border-border hover:bg-surface-subtle focus-visible:outline-focus"
          >
            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Retry query</span>
          </button>
        </div>
      )}

      {/* Result Layout: 2 Columns at 1024px and wider (60% / 40%), stacked below */}
      {data && !isLoading && !isFetching && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Answer Column (~60%) */}
          <div className="lg:col-span-7 space-y-5">
            {/* Answer Box */}
            <div
              className="p-5 bg-surface border border-border rounded-panel space-y-4"
              role="region"
              aria-label="Answer summary"
            >
              <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                Answer
              </h2>

              {isNotFound ? (
                <div className="p-4 bg-surface-subtle border border-border rounded-panel text-sm text-text-muted">
                  No answer found in the indexed tickets, notes, and records.
                </div>
              ) : (
                <div className="text-body text-text font-normal leading-prose max-w-prose whitespace-pre-wrap">
                  {data.answer}
                </div>
              )}

              {/* People Involved Chips */}
              {data.people && data.people.length > 0 && (
                <div className="pt-3 border-t border-border">
                  <div className="flex items-center gap-1.5 text-xs text-text-muted mb-2">
                    <Users className="w-3.5 h-3.5" aria-hidden="true" />
                    <span className="font-semibold uppercase tracking-wider">
                      People involved
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {data.people.map((person, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2.5 py-1 rounded-control text-xs border border-border bg-surface-subtle text-text"
                      >
                        {person}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Decision Summary Rows */}
            {decisionNodes.length > 0 && !isNotFound && (
              <div
                className="p-5 bg-surface border border-border rounded-panel space-y-3"
                role="region"
                aria-label="Decisions related to this query"
              >
                <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Decisions ({decisionNodes.length})
                </h2>

                <div className="space-y-2">
                  {decisionNodes.map((node) => {
                    const props = node.properties || {};
                    const title = (props.title as string) || node.id;
                    const status = (props.status as string) || 'active';
                    const rationale = (props.rationale as string) || '';
                    const systemName = props.system as string | undefined;
                    const lineConfig = getSystemLine(systemName);

                    return (
                      <div
                        key={node.id}
                        className="p-3 bg-surface-subtle border border-border rounded-panel space-y-1.5"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <span className="font-semibold text-sm text-text">
                            {title}
                          </span>
                          <StatusMarker
                            health={status}
                            lineColor={lineConfig.lightColor}
                            showLabel
                          />
                        </div>

                        {rationale && (
                          <p className="text-xs text-text-muted leading-relaxed line-clamp-3">
                            {rationale}
                          </p>
                        )}

                        {systemName && (
                          <div className="flex items-center gap-1.5 pt-1 text-xs">
                            <span className="text-text-muted">System:</span>
                            <span className="font-medium text-text">
                              {systemName}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Sources List */}
            {data.citations && data.citations.length > 0 && !isNotFound && (
              <div
                className="p-5 bg-surface border border-border rounded-panel space-y-3"
                role="region"
                aria-label="Evidence sources"
              >
                <h2 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                  Sources ({data.citations.length})
                </h2>

                <ul className="space-y-2 list-none p-0 m-0">
                  {data.citations.map((citation, idx) => (
                    <li key={idx}>
                      <button
                        type="button"
                        onClick={() => handleOpenSource(citation)}
                        className="w-full text-left p-3 rounded-panel border border-border bg-surface-subtle hover:bg-surface hover:border-primary transition-colors flex items-center justify-between gap-3 focus-visible:outline-focus"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {citation.type === 'meeting' ? (
                            <Users
                              className="w-4 h-4 text-primary shrink-0"
                              aria-hidden="true"
                            />
                          ) : (
                            <FileText
                              className="w-4 h-4 text-primary shrink-0"
                              aria-hidden="true"
                            />
                          )}
                          <span className="font-mono text-xs font-semibold text-text shrink-0">
                            {citation.id}
                          </span>
                          <span className="text-xs text-text truncate">
                            {citation.title}
                          </span>
                        </div>

                        <span className="text-xs font-medium text-text-muted shrink-0">
                          View details
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Evidence Column (~40%) */}
          <div className="lg:col-span-5 flex flex-col">
            <CytoscapeGraph
              graphPath={data.graph_path}
              citations={data.citations}
              onSelectNode={(nodeId, nodeType) => {
                const matchedCitation = data.citations?.find(
                  (c) => c.id === nodeId || c.title === nodeId
                );
                if (matchedCitation) {
                  handleOpenSource(matchedCitation);
                } else {
                  handleOpenSource({
                    id: nodeId,
                    title: nodeId,
                    type: (nodeType.toLowerCase() as Citation['type']) || 'document',
                  });
                }
              }}
              className="h-full min-h-[500px]"
            />
          </div>
        </div>
      )}

      {/* Right Side Source Drawer */}
      <SourceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        citation={selectedCitation}
        graphPath={data?.graph_path}
      />
    </div>
  );
};
