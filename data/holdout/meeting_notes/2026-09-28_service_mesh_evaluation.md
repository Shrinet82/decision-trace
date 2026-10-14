# Service Mesh Evaluation and Gateway Consensus
Date: 2026-09-28
Attendees: Evan Wright, Diana Prince, Alice Vance

The platform working group met to address mutual TLS between microservices. Evan argued for Istio sidecars while Diana was concerned about the 50MB memory overhead per pod. In the end, Alice Vance settled the debate by selecting Cilium Service Mesh with eBPF for inter-service encryption without sidecars.
