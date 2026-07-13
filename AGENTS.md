# Agent Instructions

## Tailscale And Happy Testing

- Assume the user is remote and connected through Tailscale.
- Use `hyggan-system-product-name.tail19f0b5.ts.net` as the canonical host. The
  current IPv4 fallback is `100.97.118.89`; verify it at runtime before use.
- Keep the established endpoints stable: Happy dev Metro on `8088`, LiveKit on
  `10000`, token service on `8443`, and room `voice`.
- The Happy dev app connects to Metro at
  `http://hyggan-system-product-name.tail19f0b5.ts.net:8088`. JS-only changes
  require a reload, not an APK reinstall.
- Preview and production are separate installed EAS builds. Keep them valid and
  test the requested channel; they do not connect to Metro.
- Use Tailscale Serve only, never Funnel. Verify routes report `tailnet only`.

## Default Voice Test Profile

- Start a fresh `happy acp opencode` session for each acceptance test run.
- Use a cheap or free OpenCode model in that session.
- Keep the voice brain in `direct` mode unless specifically testing local or
  cloud conversational routing.
- Point `VOICE_SESSION_ID` at the newly created OpenCode ACP-backed Happy session.
