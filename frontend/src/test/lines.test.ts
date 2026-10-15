import { describe, it, expect } from 'vitest';
import { getSystemLine, CATEGORY_LINES } from '../config/lines';

describe('System Category Line Mappings', () => {
  it('maps messaging systems correctly', () => {
    expect(getSystemLine('Kafka').id).toBe('messaging');
    expect(getSystemLine('RabbitMQ').id).toBe('messaging');
    expect(getSystemLine('rabbitmq').lightColor).toBe('#C72C7A');
  });

  it('maps identity and security systems correctly', () => {
    expect(getSystemLine('Keycloak').id).toBe('identity');
    expect(getSystemLine('Vault').id).toBe('identity');
    expect(getSystemLine('keycloak').lightColor).toBe('#12807A');
  });

  it('maps data systems correctly', () => {
    expect(getSystemLine('Postgres').id).toBe('data');
    expect(getSystemLine('Redis').id).toBe('data');
    expect(getSystemLine('ClickHouse').id).toBe('data');
    expect(getSystemLine('Snowflake').id).toBe('data');
    expect(getSystemLine('Elasticsearch').id).toBe('data');
  });

  it('maps observability systems correctly', () => {
    expect(getSystemLine('Prometheus').id).toBe('observability');
    expect(getSystemLine('Datadog').id).toBe('observability');
    expect(getSystemLine('Prometheus').lightColor).toBe('#C98A00');
  });

  it('falls back to platform for unknown systems or undefined', () => {
    expect(getSystemLine('Kubernetes').id).toBe('platform');
    expect(getSystemLine('UnknownSystem').id).toBe('platform');
    expect(getSystemLine(undefined).id).toBe('platform');
    expect(getSystemLine(null).id).toBe('platform');
  });

  it('defines 5 canonical category lines with light and dark colors', () => {
    const keys = Object.keys(CATEGORY_LINES);
    expect(keys).toEqual(['messaging', 'identity', 'data', 'observability', 'platform']);
    for (const key of keys) {
      const line = CATEGORY_LINES[key as keyof typeof CATEGORY_LINES];
      expect(line.lightColor).toMatch(/^#[0-9A-Fa-f]{6}$/);
      expect(line.darkColor).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});
