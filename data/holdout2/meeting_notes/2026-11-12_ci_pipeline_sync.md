# CI/CD Infrastructure and Build Fleet Sync
Date: 2026-11-12
Attendees: Ian Malcolm, Carlos Mendez, Fiona Gallagher

Discussed ongoing maintenance overhead of our self-managed Jenkins master and agent VM fleet. Pipeline configurations are split between Jenkinsfiles and newer GitHub Actions YAML workflows. Ian Malcolm decided that we will deprecate legacy Jenkins build agents in favor of GitHub Actions self-hosted runners, aiming for full decommissioning by Q1 2027.
