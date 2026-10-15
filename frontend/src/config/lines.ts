export type CategoryLine =
  | 'messaging'
  | 'identity'
  | 'data'
  | 'observability'
  | 'platform';

export interface LineConfig {
  id: CategoryLine;
  label: string;
  lightColor: string;
  darkColor: string;
}

export const CATEGORY_LINES: Record<CategoryLine, LineConfig> = {
  messaging: {
    id: 'messaging',
    label: 'Messaging',
    lightColor: '#C72C7A',
    darkColor: '#E55C9D',
  },
  identity: {
    id: 'identity',
    label: 'Identity and security',
    lightColor: '#12807A',
    darkColor: '#1BB5AC',
  },
  data: {
    id: 'data',
    label: 'Data',
    lightColor: '#5A47C8',
    darkColor: '#8172E5',
  },
  observability: {
    id: 'observability',
    label: 'Observability',
    lightColor: '#C98A00',
    darkColor: '#E8A71A',
  },
  platform: {
    id: 'platform',
    label: 'Platform',
    lightColor: '#5F6B76',
    darkColor: '#8A98A5',
  },
};

/**
 * System name mapping to category lines.
 * Any unlisted or unknown system falls back to 'platform'.
 */
export const SYSTEM_TO_LINE: Record<string, CategoryLine> = {
  // Messaging
  kafka: 'messaging',
  rabbitmq: 'messaging',

  // Identity and security
  keycloak: 'identity',
  vault: 'identity',

  // Data
  postgres: 'data',
  postgresql: 'data',
  redis: 'data',
  clickhouse: 'data',
  snowflake: 'data',
  elasticsearch: 'data',

  // Observability
  prometheus: 'observability',
  datadog: 'observability',

  // Platform
  kubernetes: 'platform',
  k8s: 'platform',
  docker: 'platform',
};

/**
 * Resolve a system name to its category line config.
 */
export function getSystemLine(systemName?: string | null): LineConfig {
  if (!systemName) {
    return CATEGORY_LINES.platform;
  }
  const normalized = systemName.trim().toLowerCase();
  const lineKey = SYSTEM_TO_LINE[normalized] ?? 'platform';
  return CATEGORY_LINES[lineKey];
}
