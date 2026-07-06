# AI Tools — token-reduction toolchain

This directory bootstraps the AI dev tooling we run on top of **happy**
(Claude Code "on the go"). One command sets it up on a fresh machine and the
tools cut token usage on every session.

```bash
./ai-tools/setup.sh          # install + wire everything (idempotent)
./ai-tools/happy-hr.sh       # launch happy routed through the compressor
```

## What we run and why

| Tool | What it does | Why we use it | Savings | How it hooks in |
|------|--------------|---------------|---------|-----------------|
| **[rtk](https://github.com/rtk-ai/rtk)** | Rust CLI proxy that filters/compresses command output (git, tests, logs, `ls`, `grep`…) before it reaches the model. | Bash tool output is the biggest source of junk tokens — repeated log lines, boilerplate, noise. rtk collapses it with <10ms overhead, zero deps. | 60–90% on common dev commands (`git push` ~200→~10 tokens). | Claude Code / happy **`PreToolUse` hook** in `~/.claude/settings.json` (`rtk hook claude`). Rewrites Bash calls transparently. |
| **[headroom](https://github.com/headroomlabs-ai/headroom)** | Local context-compression **proxy**. Compresses tool outputs, files, RAG chunks, and history, and aligns cache prefixes, before the request hits the LLM. | Shrinks the *whole* request, not just Bash — plus KV-cache alignment for better cache hits. AST-aware code compression (the `:code` image). | 15–20% for coding agents; up to 60–95% on JSON. | Runs as a Docker container on `127.0.0.1:8787`. happy points Claude Code at it via `--claude-env ANTHROPIC_BASE_URL=…` (see `happy-hr.sh`). |

**Runtime host:** [happy](https://happy.engineering) — wraps Claude Code and
adds mobile/remote control. Both tools target Claude Code, which happy spawns,
so they apply to happy sessions unchanged.

## How the pieces fit

```
                     rtk hook (PreToolUse)
                     rewrites Bash output
                              |
  you ── happy ── Claude Code ┴──► headroom proxy ──► Anthropic API
         (--claude-env         (127.0.0.1:8787,        (real upstream)
          ANTHROPIC_BASE_URL)   compress + cache-align)
```

- **rtk** works on its own the moment the hook is registered (restart happy).
- **headroom** only applies when you launch via `happy-hr.sh` (or set
  `ANTHROPIC_BASE_URL` yourself). Plain `happy` bypasses it — easy on/off.

## Verify

```bash
rtk gain                 # cumulative rtk token savings
docker logs headroom     # headroom proxy activity / health
docker ps                # confirm the headroom container is up
```

Inside a session, `git status` should come back compressed once rtk's hook is
loaded.

## New machine

`setup.sh` is the whole story — it installs rtk, registers the hook, installs
Docker if missing (via `apt`, needs sudo), pulls the headroom image, and starts
the proxy as a restart-on-boot service. Re-running it is safe.

## Caveats

- **Docker + sudo:** installing Docker Engine needs sudo; run `setup.sh` in a
  terminal where you can enter your password. After the group change, log out/in
  (or `newgrp docker`) for non-root `docker`.
- **Python 3.14:** headroom's native CLI pricing dep (LiteLLM) won't install on
  3.14+, which is why we run it via Docker instead of `pip`.
- **Auth pass-through:** happy authenticates Claude Code via OAuth. headroom
  forwards requests to Anthropic; if a session errors only when routed through
  the proxy, launch plain `happy` and check `docker logs headroom`.
- **rtk built-ins:** the rtk hook only rewrites the **Bash** tool. `Read`,
  `Grep`, `Glob` bypass it — use shell commands or `rtk read/grep/find` when you
  want compression there.

## Uninstall

```bash
rtk init -g --uninstall          # remove rtk hook + RTK.md
docker rm -f headroom            # stop/remove the headroom proxy
```
