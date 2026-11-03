# Redaction: ideas beyond #3

Parked on purpose; #3 builds known values, key names and structure, known key formats, and an entropy backstop, all deterministic and local, failing closed.

- **Live-credential validation.** Test a found key against its service to learn if it is live. Not useful for the guard (a dead key must still be redacted) and it sends the user's credential to a third party. Only as a separate opt-in "which secrets are live" feature.
- **Context-aware ML scanner.** A fast local model that reads the surrounding text to judge a suspect string. Loses reproducibility; revisit if the redaction report shows over-redaction hurting labels.
- **Uncertainty score with escalation.** Low-confidence matches get a deeper local check instead of a flat redact. Escalation must stay local: a remote model reading the suspect text is the leak.
- **Redaction report.** Record which layer fired and how often, so over-redaction can be measured before building any of the above.
