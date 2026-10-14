# Caching Architecture Follow-up
Date: 2026-10-02
Attendees: Bob Martin, Alice Vance, Ian Malcolm

We reviewed the memory consumption of local in-memory Guava caching inside service pods after last month's OOM kills. Alice Vance overturned the previous guidance for in-memory pod caching, choosing instead to route all distributed session state through the centralized Keycloak cache.
