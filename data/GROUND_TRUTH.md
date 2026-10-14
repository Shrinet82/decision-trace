# Company Brain Synthetic Ground Truth Specification

This document provides the benchmark ground truth for evaluating the Decision-Trace knowledge extraction and entity resolution pipeline against the synthetic dataset in `data/`.

---

## 1. Company Organization (SQLite `data/company.db`)
- **Company**: NovaScale Technologies
- **Teams (4)**:
  - `Core Infrastructure` (Lead: Alice Vance)
  - `Data Platform` (Lead: Carlos Mendez)
  - `Security & IAM` (Lead: Diana Prince)
  - `Developer Experience` (Lead: Hannah Abbott)
- **Projects (6)**:
  - `Project Horizon` (Lead: Alice Vance)
  - `Project Nexus` (Lead: Bob Martin)
  - `Project Titan` (Lead: Carlos Mendez)
  - `Project Shield` (Lead: Julia Roberts)
  - `Project Beacon` (Lead: Kevin Flynn)
  - `Project Velocity` (Lead: Oliver Queen)
- **Systems & Vendors (12)**:
  - `Postgres` (Owner: Evan Wright)
  - `Redis` (Owner: Alice Vance)
  - `ClickHouse` (Owner: Carlos Mendez)
  - `Keycloak` (Owner: Julia Roberts)
  - `Kafka` (Owner: Alice Vance)
  - `RabbitMQ` (Owner: Bob Martin)
  - `Elasticsearch` (Owner: Marcus Aurelius) **[OWNER-LEFT CASE]**
  - `Kubernetes` (Owner: Laura Croft)
  - `Snowflake` (Owner: Fiona Gallagher)
  - `Vault` (Owner: Diana Prince)
  - `Prometheus` (Owner: Kevin Flynn)
  - `Datadog` (Owner: Kevin Flynn)

### The Owner-Left Case (Orphaned System)
- **Person**: `Marcus Aurelius` (Former Staff Architect, Core Infrastructure)
- **Start Date**: `2021-01-10`
- **Leave Date**: `2025-11-30` (Inactive)
- **System Owned**: `Elasticsearch`
- **Audit Flag**: `Elasticsearch` is currently owned by a departed employee with no active successor assigned in SQL metadata.

---

## 2. Planted Decisions Catalog (16 Total)

| ID | Decision Title | Decided By | System | Source Document | Status |
|---|---|---|---|---|---|
| D01 | Migrate session storage from Postgres to Redis cluster | Alice Vance | Redis | `TICK-101` | Superseded by D02 |
| D02 | Migrate session storage to embedded Keycloak cache | Alice Vance | Keycloak | `TICK-102` | Accepted (Supersedes D01) |
| D03 | Adopt Snowflake for analytics ETL queries | Fiona Gallagher | Snowflake | `TICK-103` | Superseded by D04 |
| D04 | Migrate analytics reporting queries from Snowflake to ClickHouse cluster | Carlos Mendez | ClickHouse | `TICK-104` | Accepted (Supersedes D03) |
| D05 | Use Kafka for all event messaging across services | Alice Vance | Kafka | `TICK-105` | Contradicted by D06 |
| D06 | Use RabbitMQ for all event messaging across services | Bob Martin | RabbitMQ | `TICK-106` | Contradicts D05 |
| D07 | Store secret credentials exclusively in HashiCorp Vault instead of Kubernetes secrets | Diana Prince | Vault | `TICK-107` | Accepted |
| D08 | Standardize application traces on Datadog APM across all production services | Kevin Flynn | Datadog | `TICK-108` | Superseded by D14 |
| D09 | Deploy Prometheus Operator on all Kubernetes staging clusters | Laura Croft | Prometheus | `TICK-109` | Accepted |
| D10 | Deprecate legacy RabbitMQ clusters in favor of native Redis PubSub for low-volume notifications | Ian Malcolm | Redis | `TICK-110` | Accepted |
| D11 | Use Keycloak OAuth2 tokens for internal API gateway authentication | Julia Roberts | Keycloak | `TICK-111` | Accepted |
| D12 | Upgrade all production Postgres instances to version 16 | Evan Wright | Postgres | `TICK-112` | Accepted |
| D13 | Adopt Keycloak for company-wide single sign-on | Julia Roberts | Keycloak | `2026-02-10_iam_modernization.md` | Accepted |
| D14 | Migrate application metrics from Datadog to Prometheus Operator | Kevin Flynn | Prometheus | `2026-04-12_observability_sync.md` | Accepted (Supersedes D08) |
| D15 | Rotate all database passwords into Vault dynamic secrets | Diana Prince | Vault | `2026-06-08_secrets_management.md` | Accepted |
| D16 | Standardize on Kubernetes 1.30 across all production regions | Laura Croft | Kubernetes | `2026-08-20_container_platform_upgrade.md` | Accepted |

---

## 3. Ground Truth Graph Relationships

### Supersedes Relationships (`[:supersedes]`)
1. `(D02: Keycloak Session Cache) -[:supersedes]-> (D01: Redis Session Store)` [Ticket-to-Ticket]
2. `(D04: ClickHouse Reporting) -[:supersedes]-> (D03: Snowflake Analytics)` [Ticket-to-Ticket]
3. `(D14: Prometheus Metrics) -[:supersedes]-> (D08: Datadog Traces)` [Meeting-to-Ticket]

### Contradicts Relationships (`[:contradicts]`)
1. `(D06: RabbitMQ by Bob Martin) -[:contradicts]-> (D05: Kafka by Alice Vance)` [Ticket-to-Ticket, System: Kafka/RabbitMQ conflict]

### Decided By Relationships (`[:decided_by]`)
- Alice Vance -> D01, D02, D05
- Bob Martin -> D06
- Carlos Mendez -> D04
- Diana Prince -> D07, D15
- Evan Wright -> D12
- Fiona Gallagher -> D03
- Ian Malcolm -> D10
- Julia Roberts -> D11, D13
- Kevin Flynn -> D08, D14
- Laura Croft -> D09, D16
