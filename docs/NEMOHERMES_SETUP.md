# NemoHermes setup

Workshop environment recorded on 14 September 2026. Application qualification is separate work.

## Stack

- NemoClaw 0.0.123 with OpenShell and Hermes; sandbox `tender-assistant`.
- Active model: `gpt-5.6-sol`, compatible endpoint `https://api.openai.com/v1`, upstream API `openai-responses`. The initial chat-completions route failed with a tools/reasoning incompatibility.
- Local Nemotron-3 Nano 4B vLLM remains an alternative.
- Native Hermes stdio MCP: `@digilac/simap-mcp` 1.4.0.

## New environment

Follow the pinned NVIDIA Hermes quickstart:
https://github.com/NVIDIA/NemoClaw/blob/f75f722bb4a1ec9642c8df36c8924e24500d78f0/docs/get-started/quickstart-hermes.mdx

Verify Docker and GPU passthrough before choosing local inference. The original generic Linux vLLM route required experimental options. On a new host, run `nemohermes onboard --name tender-assistant` and complete provider setup interactively. Inspect an existing sandbox before changing it. Use the installed `nemohermes inference set --help` flow for inference; keep credentials outside Git.

See [SIMAP setup](../integrations/simap/README.md) and [optional dashboard ingress](../deploy/hermes-ingress/README.md). This is a runbook, not a clean-machine-tested installer.

## State ownership

Base config: `/sandbox/.hermes/config.yaml`. Dashboard profile: `/sandbox/.hermes/profiles/dashboard-home/config.yaml`. Merge individual settings, preserving unrelated configuration. Private `.hermes` state includes credentials, sessions, memory and databases. The host `~/.nemoclaw/source/AGENTS.md` belongs to upstream NemoClaw.

## Recorded verification and recovery

The workshop passed actual model completion, discovery of 14 SIMAP tools in both profiles, and in-agent calls returning 26 cantons and source-linked tenders. Full document qualification and NAT pipeline integration are not established by those tests.

On 14 September the dashboard relay from port 18789 to 19119 disappeared, causing nginx 502 while the dashboard stayed healthy inside its separate OpenShell network namespace. The original trigger is unproven. A direct probe outside that namespace was misleading. A gateway restart then failed startup checks; MCP discovery waiting up to 120 seconds was a possible contributor, not a proven cause. A manually launched relay did not persist.

Recovery backed up the base config, set SIMAP `connect_timeout: 10` and `lazy: true`, and restarted only the sandbox container to restore supervised processes. The dashboard profile was not modified by that adjustment. Subsequent checks: dashboard/API 200, real SIMAP chat returning 26 cantons, over two minutes of uptime, 53 successful nginx requests and 8 WebSocket upgrades with zero sampled upstream errors. Model and nginx containers were preserved. Repeat verification after rebuilds; do not use manual relay creation as a routine setup step.
