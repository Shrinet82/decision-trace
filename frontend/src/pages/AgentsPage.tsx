import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { PageFrame } from '../components/PageFrame';
import { btnOutline } from '../components/ui';
import { CLIENT_SNIPPETS, MCP_TOOLS, MCP_URL } from '../config/mcp';

const CopyButton: React.FC<{ text: string; label: string }> = ({ text, label }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard can be blocked; the text is selectable on the page.
    }
  };
  return (
    <button type="button" onClick={copy} className={btnOutline} aria-label={copied ? `${label}: copied` : label}>
      {copied ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
};

export const AgentsPage: React.FC = () => (
  <PageFrame header={<h1 className="m-0 text-sm font-medium text-text">Connect an agent</h1>}>
    <div className="mx-auto flex max-w-[820px] flex-col gap-8 px-5 py-8 min-[900px]:px-10">
      <p className="m-0 max-w-prose text-muted">
        Decision Trace is an MCP server. Any MCP-capable agent can ask it why decisions were made, what a
        change would affect and who to talk to, and get answers with DEC codes and sources. Six tools only
        read; <code className="rounded bg-hover px-1 text-text">add_source</code> writes demo data that resets itself
        after 10 idle minutes.
      </p>

      <section aria-labelledby="endpoint-heading" className="flex flex-col gap-2">
        <h2 id="endpoint-heading" className="m-0 text-sm font-semibold">
          Endpoint
        </h2>
        <div className="flex flex-wrap items-center gap-2 rounded-panel border border-divider bg-subtle p-2 pl-3">
          <code data-testid="mcp-url" className="min-w-0 flex-1 break-all text-sm">
            {MCP_URL}
          </code>
          <CopyButton text={MCP_URL} label="Copy endpoint URL" />
        </div>
        <p className="m-0 text-xs text-muted">Streamable HTTP, no sign-in. Limited to 20 calls a minute per IP.</p>
      </section>

      <section aria-labelledby="clients-heading" className="flex flex-col gap-4">
        <h2 id="clients-heading" className="m-0 text-sm font-semibold">
          Add it to your client
        </h2>
        {CLIENT_SNIPPETS.map((s) => (
          <div key={s.id} className="flex flex-col gap-1.5">
            <h3 className="m-0 text-sm font-medium">{s.label}</h3>
            <p className="m-0 text-xs text-muted">{s.where}</p>
            <div className="flex items-start gap-2 rounded-panel border border-divider bg-subtle p-2 pl-3">
              <pre
                tabIndex={0}
                aria-label={`${s.label} configuration`}
                className="m-0 min-w-0 flex-1 overflow-x-auto py-1 text-[13px] leading-5"
              >
                <code>{s.code}</code>
              </pre>
              <CopyButton text={s.code} label={`Copy ${s.label} configuration`} />
            </div>
            <p className="m-0 text-xs text-muted">
              Format from{' '}
              {s.docs.map((d, i) => (
                <React.Fragment key={d.href}>
                  {i > 0 && ', '}
                  <a href={d.href} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                    {d.label}
                  </a>
                </React.Fragment>
              ))}
            </p>
          </div>
        ))}
      </section>

      <section aria-labelledby="tools-heading" className="flex flex-col gap-2">
        <h2 id="tools-heading" className="m-0 text-sm font-semibold">
          Tools
        </h2>
        <ul className="m-0 list-none overflow-hidden rounded-panel border border-divider p-0">
          {MCP_TOOLS.map((t) => (
            <li key={t.name} className="flex flex-col gap-1 border-b border-row-divider px-4 py-3 last:border-b-0">
              <div className="flex items-center gap-2">
                <code className="text-sm font-semibold">{t.name}</code>
                <span className="rounded-chip border border-border px-1.5 text-xs text-muted">
                  {t.writes ? 'writes demo data' : 'read-only'}
                </span>
              </div>
              <p className="m-0 text-text-2">{t.description}</p>
              <p className="m-0 text-sm text-muted">
                Try: <span className="text-text">“{t.example}”</span>
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  </PageFrame>
);
