# Holdout Dataset Ground Truth

This document defines the ground truth annotations for 6 hand-written holdout test documents (3 tickets, 3 meeting notes).
These test documents are phrased naturally without synthetic `"decided:"` or `"decided"` markers, with decisions buried in discussions, first-name-only references, and explicit policy reversals.
This file was established **BEFORE** running any holdout extractions.

---

## 1. Holdout Tickets (`data/holdout/tickets.csv`)

### [H01] Partition audit_events table by month
- **Ticket ID**: `TICK-H01`
- **Source**: `tickets.csv`
- **System**: `Postgres`
- **Decider**: `Evan Wright` (referenced in discussion as "Evan")
- **Decision Title**: `Partition the audit_events table by month`
- **Decision Rationale**: Replace row-level TTL cron deletion with native monthly range partitioning to eliminate WAL replication bandwidth saturation.
- **Decision Status**: `accepted`
- **Phraming Characteristic**: Buried in technical discussion with no explicit "decided:" marker.

### [H02] Increase preStop sleep hook to 45 seconds across ingress deployments
- **Ticket ID**: `TICK-H02`
- **Source**: `tickets.csv`
- **System**: `Kubernetes`
- **Decider**: `Bob Martin` (referenced by first name only as "Bob")
- **Decision Title**: `Increase preStop sleep hook to 45 seconds across ingress deployments`
- **Decision Rationale**: Prevent 504 gateway timeouts and dropped TCP connections during cluster autoscaler node drain events.
- **Decision Status**: `accepted`
- **Phraming Characteristic**: Decider referenced by first name only ("Bob").

### [H03] Revert jemalloc background thread defragmentation in favor of rolling node restarts
- **Ticket ID**: `TICK-H03`
- **Source**: `tickets.csv`
- **System**: `Redis`
- **Decider**: `Ian Malcolm`
- **Decision Title**: `Revert jemalloc background thread defragmentation in favor of rolling node restarts`
- **Decision Rationale**: Eliminate 20ms write latency spikes caused by background thread memory defragmentation under sustained write load.
- **Decision Status**: `reverted`
- **Phraming Characteristic**: Decision reversal of an earlier memory defragmentation approach.

---

## 2. Holdout Meeting Notes (`data/holdout/meeting_notes/`)

### [H04] Transition raw event logs older than 90 days to Glacier Flexible Archive
- **Meeting Note**: `2026-09-15_data_retention_sync.md`
- **Date**: `2026-09-15`
- **System**: `Snowflake` / `S3`
- **Decider**: `Carlos Mendez`
- **Decision Title**: `Transition raw event logs older than 90 days to Glacier Flexible Archive`
- **Decision Rationale**: Reduce S3 cold storage tier expenditures by 60% compared to Instant Retrieval.
- **Decision Status**: `accepted`
- **Phraming Characteristic**: Buried in cost comparison discussion; phrased as "Carlos Mendez resolved that...".

### [H05] Select Cilium Service Mesh with eBPF for inter-service encryption without sidecars
- **Meeting Note**: `2026-09-28_service_mesh_evaluation.md`
- **Date**: `2026-09-28`
- **System**: `Kubernetes`
- **Decider**: `Alice Vance`
- **Decision Title**: `Select Cilium Service Mesh with eBPF for inter-service encryption without sidecars`
- **Decision Rationale**: Avoid 50MB per-pod memory overhead of Istio sidecars while enforcing mTLS.
- **Decision Status**: `accepted`
- **Phraming Characteristic**: Consensus reached after multi-attendee debate; phrased as "settled the debate by selecting...".

### [H06] Route all distributed session state through centralized Keycloak cache instead of in-memory pod caching
- **Meeting Note**: `2026-10-02_cache_strategy_reversal.md`
- **Date**: `2026-10-02`
- **System**: `Keycloak`
- **Decider**: `Alice Vance`
- **Decision Title**: `Route all distributed session state through centralized Keycloak cache instead of in-memory pod caching`
- **Decision Rationale**: Overturn previous local Guava in-memory caching to eliminate pod OOM kills.
- **Decision Status**: `accepted`
- **Phraming Characteristic**: Explicit reversal ("overturned the previous guidance... choosing instead to...").
