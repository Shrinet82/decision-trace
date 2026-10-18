import type { AskStreamEvent, BatchEvent, GithubEvent, IngestEvent } from './types';

/** One dispatched server-sent event, before its data is decoded. */
export interface SseMessage {
  event: string;
  data: string;
}

export interface SseParseResult {
  events: SseMessage[];
  /** Unterminated tail of the buffer; prepend it to the next chunk. */
  rest: string;
}

function parseBlock(block: string): SseMessage | null {
  let event = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value || 'message';
    else if (field === 'data') data.push(value);
    // id and retry are not used by this client
  }
  if (data.length === 0) return null;
  return { event, data: data.join('\n') };
}

/**
 * Pure server-sent-events parser. Pass the previous `rest` plus the newly decoded chunk; get back
 * every complete event and the leftover text. Handles LF, CRLF and CR line endings, events split
 * across chunks (even between a CR and its LF), several events per chunk, comments and multi-line
 * data fields.
 */
export function parseSse(buffer: string): SseParseResult {
  let text = buffer;
  let held = '';
  // A trailing CR may be the first half of a CRLF split across chunks: decide once more arrives.
  if (text.endsWith('\r')) {
    held = '\r';
    text = text.slice(0, -1);
  }
  text = text.replace(/\r\n?/g, '\n');

  const events: SseMessage[] = [];
  let start = 0;
  let end: number;
  while ((end = text.indexOf('\n\n', start)) !== -1) {
    const message = parseBlock(text.slice(start, end));
    if (message) events.push(message);
    start = end + 2;
  }
  return { events, rest: text.slice(start) + held };
}

const INGEST_EVENT_NAMES = new Set(['step', 'graph', 'diff', 'error']);

/** Decodes the JSON payload of an ingest event. Unknown event names and bad JSON are skipped. */
export function toIngestEvent(message: SseMessage): IngestEvent | null {
  if (!INGEST_EVENT_NAMES.has(message.event)) return null;
  try {
    const data = JSON.parse(message.data) as unknown;
    if (!data || typeof data !== 'object') return null;
    return { event: message.event, data } as IngestEvent;
  } catch {
    return null;
  }
}

const ASK_EVENT_NAMES = new Set(['step', 'query', 'path', 'token', 'done', 'error']);

/** Decodes the JSON payload of an /ask/stream event. Unknown event names and bad JSON are skipped. */
export function toAskEvent(message: SseMessage): AskStreamEvent | null {
  if (!ASK_EVENT_NAMES.has(message.event)) return null;
  try {
    const data = JSON.parse(message.data) as unknown;
    if (!data || typeof data !== 'object') return null;
    return { event: message.event, data } as AskStreamEvent;
  } catch {
    return null;
  }
}

const BATCH_EVENT_NAMES = new Set(['files', 'file', 'step', 'graph', 'diff', 'error']);

/** Decodes the JSON payload of a /ingest/batch event. Unknown event names and bad JSON are skipped. */
export function toBatchEvent(message: SseMessage): BatchEvent | null {
  if (!BATCH_EVENT_NAMES.has(message.event)) return null;
  try {
    const data = JSON.parse(message.data) as unknown;
    if (!data || typeof data !== 'object') return null;
    return { event: message.event, data } as BatchEvent;
  } catch {
    return null;
  }
}

const GITHUB_EVENT_NAMES = new Set(['progress', 'diff', 'error']);

/** Decodes the JSON payload of a /ingest/github event. Unknown event names and bad JSON are skipped. */
export function toGithubEvent(message: SseMessage): GithubEvent | null {
  if (!GITHUB_EVENT_NAMES.has(message.event)) return null;
  try {
    const data = JSON.parse(message.data) as unknown;
    if (!data || typeof data !== 'object') return null;
    return { event: message.event, data } as GithubEvent;
  } catch {
    return null;
  }
}
