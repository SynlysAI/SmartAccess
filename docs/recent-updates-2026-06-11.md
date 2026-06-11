# Recent Updates 2026-06-11

## Summary

This note captures the implementation changes that landed after the original v2 simplification baseline. It is an additive update to `README.md`, `docs/PRD.zh-CN.md`, `docs/SPEC.zh-CN.md`, and the contract examples.

## UDP Workspace Assets

- Added a directly runnable UDP calibration profile in `workspace/anchors/serial_debug_assistant_udp/anchors.yaml`.
- Added the matching legacy instrument projection in `workspace/instruments/serial_debug_assistant_udp/instrument_profile.yaml`.
- Added a runnable draft workflow in `workspace/workflows/wf_serial_debug_assistant_udp_send/draft.yaml`.
- The workflow targets local UDP port `8889`, sends `SmartAccess UDP validation`, and uses OCR on the right-side log area to verify the send result.
- The workspace anchor profile uses a `1322x914` capture baseline and includes anchors such as:
  - `protocol_mode_udp`
  - `local_port_input`
  - `open_udp_button`
  - `send_text_input`
  - `send_button`

## Multi-Model AI Integration

- Workflow draft generation and calibration-page anchor suggestion now share one OpenAI-compatible chat adapter.
- The desktop calibration page exposes temporary overrides for:
  - `AI provider`
  - `AI base URL`
  - `AI model`
- API keys are still expected from environment configuration and are not written into workspace files.
- Legacy DeepSeek generators remain available, but now delegate to the shared OpenAI-compatible implementation.

## Vision Context for Calibration AI

- When the calibration page has a captured window screenshot, the AI request includes that image as a `data:image/...;base64,...` payload.
- The anchor-generation prompt is constrained to the simplified `anchors.yaml` model.
- OCR-related anchor suggestions are expressed only through `observe_region`.

## Environment Configuration

- Added generic AI settings:
  - `SMARTACCESS_AI_PROVIDER`
  - `SMARTACCESS_AI_BASE_URL`
  - `SMARTACCESS_AI_MODEL`
  - `SMARTACCESS_AI_API_KEY`
  - `SMARTACCESS_AI_TIMEOUT_SECONDS`
  - `SMARTACCESS_AI_USER_AGENT`
- `DEEPSEEK_*` settings remain backward-compatible.
- The runtime now auto-loads the project-root `.env` file. Real process environment variables still take precedence over `.env`.

## Gateway Compatibility

- OpenAI-compatible requests now send:
  - `User-Agent`
  - `Accept-Language`
  - `Origin`
  - `Referer`
- Cloudflare `403 / 1010` responses are collapsed into a short actionable error message instead of surfacing the full upstream JSON payload.

## Verification

- `python -m pytest tests/integration/test_services.py -q`
- `python -m pytest tests/contract/test_contract_examples.py -q`
- `python -m pytest tests/desktop/test_shell_smoke.py::test_calibration_page_exposes_simplified_anchor_table -q`
- `python -m compileall -q src\\smartaccess`
