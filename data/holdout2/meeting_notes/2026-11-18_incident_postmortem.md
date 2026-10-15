# Incident Postmortem: Checkout Timeout Surge
Date: 2026-11-18
Attendees: Dave Miller, Bob Martin, Julia Roberts

Reviewed the timeline of Sunday's 14-minute error rate elevation on the checkout service during flash sale traffic.
Database connection pool peaked at max capacity (150 connections) due to high concurrency.
Bob Martin shared telemetry graphs showing connection queue wait times reached 4.2 seconds.
Dave Miller reviewed PgBouncer log levels.
No architecture or policy changes were decided during this postmortem; follow-up profiling items will be assigned in next week's operational triage.
