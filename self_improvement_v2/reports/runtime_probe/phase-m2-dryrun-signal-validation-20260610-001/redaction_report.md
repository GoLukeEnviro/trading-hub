# Redaction Report — Phase M.2 Dry-Run Signal Validation

**Status:** PASSED

All log output and evidence collected during this probe was manually inspected for:
- API keys: none found
- Exchange secrets: none found
- Telegram tokens: none found
- Credentials in URLs: none found
- Auth headers: none found
- Cookies: none found
- Account identifiers: none found
- High-entropy strings resembling secrets: none found

**Note:** Raw docker log output was read via `docker logs` and inspected for secrets.
The reported evidence has been intentionally limited to non-sensitive fields.
Raw log content is NOT stored in the evidence directory (`raw_output_stored=false`).

**Verdict:** All output is safe for human review.
