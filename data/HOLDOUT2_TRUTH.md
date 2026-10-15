# Holdout 2 Ground Truth Dataset (Anti-Overfitting Validation)

Established **BEFORE** prompt tuning or two-pass extraction implementation in Step 7.
Contains 8 test documents (4 tickets, 4 meeting notes) with a realistic mix:
- 1 obvious decision (`H201`)
- 1 maintenance-style decision (`H202`)
- 1 buried decision in technical discussion (`H203`)
- 1 standardization decision (`H204`)
- 1 deprecation decision (`H205`)
- 3 negative documents containing NO decisions (bug report, incident postmortem, weekly standup)

---

## Expected Holdout 2 Decisions

| ID | Title | System | Decided By | Source | Status | Rationale / Evidence |
|---|---|---|---|---|---|---|
| **H201** | Adopt OpenTelemetry for distributed tracing across all microservices | OpenTelemetry | Alice Vance | TICK-H201 | accepted | Replaces ad-hoc logging with W3C trace context propagation. |
| **H202** | Upgrade Elasticsearch cluster to version 8.13 across all logging nodes | Elasticsearch | Carlos Mendez | TICK-H202 | accepted | Upgraded to enable vector indexing and fix memory pressure in Lucene. |
| **H203** | Reduce TCP keepalive probe timeout to 60 seconds on egress gateways | Kubernetes | Dave Miller | TICK-H203 | accepted | Buried in packet analysis: resolves silent AWS NAT gateway connection drops. |
| **H204** | Standardize on Envoy proxy as the unified ingress gateway for all public services | Envoy | Laura Croft | 2026-11-05_gateway_standardization.md | accepted | Eliminates fragmented NGINX and HAProxy configurations across regions. |
| **H205** | Deprecate legacy Jenkins build agents in favor of GitHub Actions self-hosted runners | Jenkins | Ian Malcolm | 2026-11-12_ci_pipeline_sync.md | accepted | Cuts CI maintenance overhead and unifies CI/CD pipelines under single workflow format. |

---

## Negative Documents (Expected: 0 Decisions Extracted)

1. **`TICK-H204`**: High memory usage in notification worker pod. Root-caused to third-party XML parser leak, pod restarted with bumped memory limit. Standard operational triage, no architectural or process decision.
2. **`2026-11-18_incident_postmortem.md`**: Postmortem on checkout timeout during marketing campaign. Review of error rates and database connection pools. No decisions or policy changes finalized.
3. **`2026-11-25_weekly_standup.md`**: Sprint standup covering sprint burndown, vacation schedules, and task assignments. Routine status sharing, no decisions.
