# Test evidence

How to produce the evidence (inside `backend\`):

```powershell
..\.venv\Scripts\python -m pytest -v --junitxml=reports\test_results.xml | Tee-Object reports\test_results.txt
```

Last recorded full run: **69 passed** (2026-10-23, before the backend/ frontend restructure). Re-run the command above
after any change and attach `reports\test_results.txt` to the submission. Additional evidence: the benchmark's
`security_attempts.csv`, the Analytics page and the live verdicts on the Live demo.

| # | Requirement | Test(s) | Expected | Observed | Evidence |
|---|---|---|---|---|---|
| 1 | A valid client can connect | `test_valid_device_message_reaches_gateway`, `test_tls_valid_client_connects_with_tls13_and_ecdsa`, `test_mtls_valid_device_connects_and_cn_is_username` | connects, message delivered | TLS 1.3, `TLS_AES_128_GCM_SHA256`, peer CN=localhost | pytest output; Live demo "Send sensor reading" ✅ |
| 2 | Untrusted certificate rejected | `test_client_rejects_untrusted_broker`, `test_mtls_bad_client_certificates_rejected[rogue_client]` | rejected | broker log `certificate verify failed`; client `self-signed certificate in certificate chain` | benchmark `security_attempts.csv` 5/5 |
| 3 | Invalid / mismatched identity rejected | `test_hostname_mismatch_rejected`, `[expired_client]`, `[server_as_client]`, `test_mtls_device_cannot_impersonate_another_device` | rejected | hostname mismatch refused; expired + wrong-EKU refused in the handshake | pytest; Live demo attack buttons |
| 4 | Missing / invalid credentials rejected | `test_wrong_password_is_rejected`, `test_anonymous_is_rejected`, `test_unknown_user_is_rejected`, `test_tls_wrong_password_rejected`, `test_mtls_no_client_cert_rejected` | rejected | CONNACK `Not authorized`; `peer did not return a certificate` | Analytics "Login refused" |
| 5 | Unauthorised client cannot publish to protected topics | `test_device_cannot_impersonate_another_device`, `test_device_cannot_publish_fake_validated_telemetry` | not delivered | broker logs `Denied PUBLISH`; nothing received | Live demo "Impersonate dev-002" |
| 6 | Cannot subscribe without permission | `test_device_cannot_read_other_data[ingest/+, ingest/dev-002, sensors/+/telemetry, #]` | no data delivered | Mosquitto 2.1.2 returns SUBACK "Granted QoS 1" **but delivers nothing** (read ACL checked per message) | pytest |
| 7 | Invalid schemas rejected by the application | `tests/test_schema.py` (20+ cases), `test_invalid_message_rejected_and_reported`, `test_replayed_message_rejected` | rejected, reported on `gateway/events` | out-of-range, missing field, wrong types, NaN, mismatched ID, extra fields, replay all rejected | Analytics "Invalid message", "Replayed message" |
| 8 | Recovers from broker disconnection | `test_gateway_recovers_after_broker_restart` | reconnects, re-subscribes, traffic flows | disconnect detected; reconnect within the backoff; telemetry delivered | pytest; `logs/gateway.log` |
| 9 | Certificate verification stays enabled | `test_no_insecure_tls_settings_in_source`, `test_client_context_is_strict` | no insecure settings | CERT_REQUIRED, check_hostname=True, TLS ≥ 1.2 | pytest |
| 10 | Private keys / secrets not committed | `tests/test_no_secrets_in_git.py` | none tracked | `git ls-files` contains no keys, passwords or DB files | pytest |

## Screenshots to capture for the report
1. Live demo, **Plain TCP**: eavesdropper capture showing READABLE JSON.
2. Live demo, **Mutual TLS**: journey card ② with the 249 B = 227 + 1 + 16 + 5 calculation, and the handshake steps.
3. Live demo: Results panel after running all attacks (all ✅).
4. Analytics page with the fleet running (KPIs, latency chart, security events).
5. Benchmarks page: key findings and latency CDF.
6. Terminal: `pytest -v` summary line.
