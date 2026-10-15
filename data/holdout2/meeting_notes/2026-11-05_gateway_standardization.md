# Gateway Architecture and Traffic Management
Date: 2026-11-05
Attendees: Laura Croft, Kevin Flynn, Alice Vance

Evaluated traffic ingress topology across US-East and EU-West regions. Currently running fragmented instances of NGINX Ingress and HAProxy, causing duplicated SSL certificate rotation logic and inconsistent header filtering. Laura Croft concluded that we will standardize on Envoy proxy as the unified ingress gateway for all public services starting next sprint.
