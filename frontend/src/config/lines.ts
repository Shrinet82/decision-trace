export type CategoryLine =
  | 'messaging'
  | 'identity'
  | 'data'
  | 'observability'
  | 'platform';

export interface LineConfig {
  id: CategoryLine;
  label: string;
  color: string;
}

export const CATEGORY_LINES: Record<CategoryLine, LineConfig> = {
  messaging: { id: 'messaging', label: 'Messaging', color: '#C72C7A' },
  identity: { id: 'identity', label: 'Identity and security', color: '#12807A' },
  data: { id: 'data', label: 'Data', color: '#5A47C8' },
  observability: { id: 'observability', label: 'Observability', color: '#C98A00' },
  platform: { id: 'platform', label: 'Platform', color: '#6B6F76' },
};

/**
 * System name mapping to category lines.
 * Any unlisted or unknown system falls back to 'platform'.
 */
export const SYSTEM_TO_LINE: Record<string, CategoryLine> = {
  kafka: 'messaging',
  rabbitmq: 'messaging',

  keycloak: 'identity',
  vault: 'identity',

  postgres: 'data',
  postgresql: 'data',
  redis: 'data',
  clickhouse: 'data',
  snowflake: 'data',
  elasticsearch: 'data',

  prometheus: 'observability',
  datadog: 'observability',

  kubernetes: 'platform',
  k8s: 'platform',
  docker: 'platform',
};

/**
 * Resolve a system name to its category line config. Composite names such as
 * "Snowflake, ClickHouse" resolve by their first known part.
 */
export function getSystemLine(systemName?: string | null): LineConfig {
  if (!systemName) {
    return CATEGORY_LINES.platform;
  }
  for (const part of systemName.split(',')) {
    const lineKey = SYSTEM_TO_LINE[part.trim().toLowerCase()];
    if (lineKey) return CATEGORY_LINES[lineKey];
  }
  return CATEGORY_LINES.platform;
}
