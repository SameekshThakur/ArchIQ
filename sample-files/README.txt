ArchIQ sample files
====================

All files are built from the seeded Northwind Assurance estate, so they reconcile with what the app already knows.
Upload them from the page named in brackets (or click "Use sample" in the upload dialog).

1. sample-cmdb-export-2026-11.xlsx / .csv        [Discovery > Import inventory]
   A ServiceNow-style CMDB export of 66 applications. Expect: 56 clean matches, 5 applications with drift
   (3 criticality, 2 stale hosting, 2 stale owners), 2 renamed systems matched by name similarity (Claim Payments Hub,
   Northwind Customer Hub v2), 2 systems unknown to the estate (Broker Commission Calculator, Claims SMS Gateway),
   1 retired record, and 6 estate applications missing from the export (the shadow IT that only code discovery found).

2. Claims-Intake-Modernization-HLD-v1.2.docx         [Documents > Upload documents]
   A Word high-level design. It agrees with the estate in most places but says Customer Notification Hub runs on
   Azure App Service while the estate and several other documents say Azure AKS, which shows up as a new conflict.

3. Policy-Admin-Operations-Runbook.pdf               [Documents > Upload documents]
   A PDF runbook. It documents the Policy Admin Core to Policy Master DB dependency that no existing document
   records, so uploading it closes GAP-001 and adds a Current-status source that confirms the estate.

4. ADR-0052-Event-Driven-Claims-Notifications.md     [Documents > Upload documents]
   An accepted architecture decision record that adds Kafka-based notification relationships.

5. claims-copilot-main.tf                            [Standards > Check a design, or Review agent]
   Terraform as deployed. Compliance score 44: breaks the private-endpoint rule (STD-SEC-014), allows TLS 1.0,
   keeps a secret in app settings, and is missing tags and diagnostics.

6. claims-copilot-main.fixed.tf                      [Standards > Check a design]
   The remediated version. Score 88 with no failures. Run it after the first to show the recovery.

7. claims-copilot-main.bicep / .fixed.bicep         [Standards > Check a design]
   The same before-and-after story written in Bicep, for teams that deploy with Bicep rather than Terraform.

8. claims-notifications-design.md                    [Review agent > Review a design]
   An ARB submission written as prose, with deliberate policy breaches (public OpenAI endpoint, API key,
   no human review of AI-drafted messages, TLS 1.0 storage). Expect a no-go verdict (readiness about 28).

9. agent-portal-sso-design.json                      [Review agent > Review a design, or New analysis]
   A compliant ARB submission with its non-functional requirements filled in. Expect a go verdict (readiness 91).
   Use it to show the "Ready" outcome; domain: Customer & Distribution.

Regenerate with:  cd backend && PYTHONPATH=. python3 -m scripts.build_samples
