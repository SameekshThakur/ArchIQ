# ADR-0052: Event-driven claims notifications

Status: Accepted
Date: 2026-10-21
Deciders: Avadhi Jain (Chief Architect), Ananya Rao (Claims Digital), Arjun Desai (Integration)
Domain: Claims

## Context
Policyholders receive status updates by SMS and email when a claim moves between stages. Today each system that changes a claim sends its own notification, which has produced duplicate messages and inconsistent wording. During storm season the volume also overloads the systems that send them.

## Decision
Claim lifecycle changes are published as events and Claims Notification Service is the only sender of policyholder messages.

Claims Notification Service integrates with Kafka Event Platform using event. Claims Intake Portal integrates with Claims Notification Service using event. Fraud Scoring Engine integrates with Claims Notification Service using event.

Message templates are owned by Claims Digital and versioned in the notification repository.

## Consequences
- One place to change wording, channels and quiet hours.
- Kafka Event Platform becomes a dependency of the claim lifecycle and must be run with the resilience of a tier 1 service.
- Teams that currently send their own notifications must migrate within two quarters.

## Alternatives considered
1. Keep per-system notifications and publish a shared style guide. Rejected: does not remove duplicates.
2. Use the vendor notification module in Guidewire ClaimCenter. Rejected: only covers claims created in that system.
