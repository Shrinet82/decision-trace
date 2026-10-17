/** Where agents connect, and what they can call. Mirrors backend/app/mcp_server.py. */
export const MCP_URL =
  import.meta.env.VITE_MCP_URL ?? 'https://decision-trace-api-production.up.railway.app/mcp';

export interface McpTool {
  name: string;
  /** What the tool does, in the words an agent reads when choosing it. */
  description: string;
  example: string;
  writes?: boolean;
}

export const MCP_TOOLS: McpTool[] = [
  {
    name: 'ask',
    description:
      'Ask a free-form question and get a grounded answer with the primary decision (DEC code), citations and the evidence path through the graph.',
    example: 'Ask Decision Trace why we use Keycloak.',
  },
  {
    name: 'get_decision',
    description:
      'One decision by DEC code: health and why, deciders, systems, supersedes and contradicts lineage, and its sources with verbatim quotes.',
    example: 'Get DEC-11 from Decision Trace and tell me if it is still valid.',
  },
  {
    name: 'list_decisions',
    description:
      'List decisions with DEC code, title and health. Filter by status (active, superseded, contradicted, possibly_stale) or by system.',
    example: 'List the contradicted decisions in Decision Trace.',
  },
  {
    name: 'impact_of',
    description:
      'What is affected if a system is dropped or changed: decisions (and which are already superseded), people to involve, teams, projects and tickets.',
    example: 'Use Decision Trace to tell me what is affected if we drop Snowflake.',
  },
  {
    name: 'who_knows',
    description:
      'People ranked by recorded evidence for a system or technology: decisions made, systems owned, meetings attended, tickets worked on. Departed people are flagged.',
    example: 'Who knows the most about Kafka? Check Decision Trace.',
  },
  {
    name: 'find_conflicts',
    description: 'Pairs of contradicting decisions and systems whose owner has left the company.',
    example: 'Does Decision Trace show any conflicting decisions or unowned systems?',
  },
  {
    name: 'add_source',
    description:
      'Add one meeting note, ticket or announcement. Decisions are extracted and compared with existing ones; returns the diff. Demo data, removed after 10 idle minutes.',
    example: 'Add these meeting notes to Decision Trace and show me what changed.',
    writes: true,
  },
];

export interface ClientSnippet {
  id: 'claude-code' | 'claude-desktop' | 'cursor';
  label: string;
  /** Where the snippet goes. */
  where: string;
  language: 'bash' | 'json';
  code: string;
  /** Official documentation the format was checked against. */
  docs: { label: string; href: string }[];
}

const NAME = 'decision-trace';

export const CLIENT_SNIPPETS: ClientSnippet[] = [
  {
    id: 'claude-code',
    label: 'Claude Code',
    where: 'Run in a terminal',
    language: 'bash',
    code: `claude mcp add --transport http ${NAME} ${MCP_URL}`,
    docs: [{ label: 'Claude Code: connect to MCP servers', href: 'https://code.claude.com/docs/en/mcp' }],
  },
  {
    id: 'claude-desktop',
    label: 'Claude Desktop',
    where: 'claude_desktop_config.json, then restart Claude Desktop',
    language: 'json',
    code: JSON.stringify(
      {
        mcpServers: {
          [NAME]: { command: 'npx', args: ['-y', 'mcp-remote', MCP_URL, '--transport', 'http-only'] },
        },
      },
      null,
      2
    ),
    docs: [
      { label: 'MCP: connect Claude Desktop to servers', href: 'https://modelcontextprotocol.io/docs/develop/connect-local-servers' },
      { label: 'mcp-remote', href: 'https://github.com/geelen/mcp-remote' },
    ],
  },
  {
    id: 'cursor',
    label: 'Cursor',
    where: '.cursor/mcp.json in a project, or ~/.cursor/mcp.json for every project',
    language: 'json',
    code: JSON.stringify({ mcpServers: { [NAME]: { url: MCP_URL } } }, null, 2),
    docs: [{ label: 'Cursor: Model Context Protocol', href: 'https://cursor.com/docs/context/mcp' }],
  },
];
