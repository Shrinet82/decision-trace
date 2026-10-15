# Ground Truth Addendum: Genuine Unplanted Decisions

> **Notice**: This document records genuine architectural, governance, and technology decisions discovered in the synthetic dataset during the Step 8 precision audit. These decisions were **found after the fact** and are NOT present in the original `data/GROUND_TRUTH.md` benchmark catalog. `data/GROUND_TRUTH.md` remains unaltered.

---

## Catalog of Genuine Unplanted Decisions

### 1. Decommission Snowflake Warehouses
- **Decision Title**: Decommission Snowflake warehouses in favor of ClickHouse
- **Decider**: Laura Croft
- **System**: Snowflake (and ClickHouse)
- **Source Document**: `data/meeting_notes/2026-10-10_cloud_cost_optimization.md`
- **Verbatim Quote**:
  > *"Notes: Reviewed monthly cloud spend reductions achieved by decommissioning Snowflake warehouses in favor of ClickHouse. Laura Croft decided: complete decommission of legacy Snowflake reporting warehouses by end of month."*
- **Rationale**: An explicit architectural decommissioning decision finalizing the ClickHouse migration and eliminating redundant cloud spend.

---

### 2. Reassign Elasticsearch Cluster Ownership
- **Decision Title**: Reassign Elasticsearch cluster ownership to Core Infrastructure
- **Decider**: Alice Vance
- **System**: Elasticsearch
- **Source Document**: `data/meeting_notes/2026-07-14_search_infrastructure_review.md`
- **Verbatim Quote**:
  > *"Notes: Discussed orphaned Elasticsearch cluster. The original system owner, Marcus Aurelius, left the company on 2025-11-30. Alice Vance decided: System ownership needs reassignment to Core Infrastructure."*
- **Rationale**: Direct governance and ownership decision resolving the orphaned system state created by Marcus Aurelius's departure.

---

### 3. Evaluate Monorepo Build Caches and PR Previews
- **Decision Title**: Evaluate monorepo build caches and automated PR previews
- **Decider**: Hannah Abbott
- **System**: Developer Experience / CI Pipeline
- **Source Document**: `data/meeting_notes/2026-09-10_dev_experience_sync.md`
- **Verbatim Quote**:
  > *"Notes: Evaluated monorepo build caches and automated PR previews. Hannah Abbott decided: initiate technical spike on build cache tooling."*
- **Rationale**: Tooling evaluation and process decision initiated by Dev Experience team lead.
