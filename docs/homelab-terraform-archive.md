# Homelab Terraform Archive

Snapshot of everything Terraform manages on the homelab, originally written
**2026-08-02** morning, refreshed **2026-08-02** evening (same day). Source
of truth is `C:\Users\cafe\WSL\infra\self-hosted` (a separate git repo from
this one). This document is a point-in-time archive, not live state — diff
it against `infra\self-hosted` before trusting specifics.

## ⚠ Known-dangerous drift, found on this refresh

**`compute`, `networking`, and `llm_server` are 100% stale and describe a
tool that no longer exists on this box.** Ollama (native Windows) was
uninstalled 2026-08-02 (see the [[local-server-setup]] memory / llama.cpp
migration), but these three modules' `.tf` and `ensure-*.ps1` files have not
been touched since 2026-07-20 — confirmed by a fresh read, not assumption —
and all three are **still tracked as applied in today's `terraform.tfstate`**
(`module.compute.terraform_data.ollama`,
`module.networking.terraform_data.firewall_rule`,
`module.llm_server.terraform_data.models`). Concretely, they still do:
`winget install --id Ollama.Ollama ...`, hit `http://127.0.0.1:<port>/api/version`,
`/api/tags`, `/api/generate`, and run `ollama.exe pull <model>`. **This means
an untargeted `terraform apply` from `infra/self-hosted` right now would try
to reinstall and manage Ollama, silently undoing today's uninstall** — root
`variables.tf`/`README.md` are still entirely Ollama-framed too, no mention
of llama.cpp anywhere. This is exactly why every `terraform apply` run
against this repo today was scoped with
`-target=module.glance.terraform_data.glance` rather than run bare — **do
not run a bare `terraform apply`/`plan` against this repo until Kyle decides
what to do with these three modules** (retire them, or rewrite for
llama.cpp) — flagging for a real decision, not guess-fixing it here.

## Architecture at a glance

```
infra/self-hosted (local backend, terraform.tfstate gitignored)
├── compute            ⚠ STALE — Ollama, native Windows (Ollama uninstalled 2026-08-02)
├── networking          ⚠ STALE — firewall rule for Ollama's WSL↔Windows path
├── llm_server           ⚠ STALE — model manifest + pull/smoke-test (depends_on compute)
├── thingsboard_pi4       ThingsBoard stack on a Raspberry Pi 4 over SSH
├── glance                This dashboard + its config-editor sidecar
├── launcher              Desktop-app launcher listener (native PowerShell)
└── jellyfin              Media server sidecar
```

Convergence pattern used everywhere except `thingsboard_pi4`: a
`terraform_data` resource with a `triggers_replace` hash of its inputs, wired
to a `local-exec` provisioner that runs an idempotent PowerShell
"ensure-*.ps1" script. `thingsboard_pi4` is the one exception — it converges
over SSH (`connection` block + `file`/`remote-exec` provisioners) since the
target is a remote Linux host, not the local Windows box.

Only one explicit inter-module dependency exists: `llm_server` →
`depends_on = [module.compute]`. Everything else is independent and can
apply/fail in isolation.

## Modules

### `compute` — Ollama (native Windows) — ⚠ STALE, see warning above

Installs Ollama via `winget` if missing, warns if no GPU is visible
(`nvidia-smi`), sets the user `OLLAMA_HOST` env var, restarts/starts the app,
polls `/api/version` until healthy. **Ollama itself was uninstalled
2026-08-02; this module was not updated to match and would try to reinstall
it on a bare apply.**

- Variables: `ollama_port` (default from root: `11434`), `ollama_bind`
  (`0.0.0.0`)
- Output: `endpoint` = `http://127.0.0.1:<port>`

### `networking` — Ollama firewall rule — ⚠ STALE, see warning above

Tests actual WSL→Windows reachability first (curl from inside WSL to the
gateway IP) and only creates a `New-NetFirewallRule` if unreachable AND no
rule already exists — Windows Firewall doesn't filter the WSL vswitch on this
box, so most of the time this is a no-op by design. Reachability check itself
hits Ollama's `/api/version`, so it no longer has anything real to check.

- Variables: `firewall_rule_name` (`Ollama-WSL`), `firewall_interface_alias`
  (`vEthernet (WSL)`), `wsl_distro` (`NixOS`)
- No outputs.

### `llm_server` — model manifest — ⚠ STALE, see warning above

Pulls any declared model not already present, then runs a smoke inference
against the first model in the list to confirm the server actually answers
(computes tok/s from the response). All of it is `ollama.exe`-specific
(`pull`, `/api/tags`, `/api/generate`) — has no awareness that llama.cpp is
now the actual LLM engine on this box.

- Variables: `models` (currently `["qwen3:0.6b"]`) — this list doubles as the
  DR/recovery manifest
- Output: `models` = the same list

### `thingsboard_pi4` — ThingsBoard on the Pi 4

Migrated from a k3s deployment on `bourbon` (see the
`thingsboard-pi4-migration` memory). Runs over SSH against the pi4 host:
copies an install script + rendered `docker-compose.yml` +
`install.env`, then remote-execs the install (podman + podman-compose,
Postgres readiness poll, one-time restore from a Tailscale Taildrop dump
guarded by a `.migrated` marker, systemd unit for the stack).

- Containers: `thingsboard-postgres` (`postgres:18`), `thingsboard-tbnode`
  (`thingsboard/tb-node`), ports `9271:8080` (UI), `1883`, `8883`, `7070`
- Variables: `host` (`pi4`, Tailscale MagicDNS), `ssh_user` (`dietpi`),
  `ssh_password` *(sensitive)*, `postgres_password` *(sensitive)*,
  `tb_version` (`4.3.1.3`), `postgres_major_version` (`18`), `java_heap_mb`
  (`3072`), `stack_dir` (`/opt/thingsboard-stack`)
- Output: `ui_url` = `http://<host>:9271`
- **Known incident (2026-07-30):** Podman's short-name image resolution
  failed on `postgres:18` (Podman needs a fully-qualified ref, unlike
  Docker's implicit Hub default) and the install script exited 1 — but
  Terraform still reported "Apply complete!" because a trailing
  `shred || rm` fallback masked the real exit code. Fixed by adding `set -e`
  to the remote-exec script.

### `glance` — this dashboard + config editor

Two sidecar containers via `nerdctl` (Rancher Desktop's containerd, not
dockerd): `glance` itself and `glance-config-editor` (a Monaco-editor page,
`python:3-alpine` + stdlib `http.server`, GET/POST on `glance.yml`).

- Secret handling: a `local_sensitive_file` writes the Claude session key to
  `C:\Users\cafe\WSL\glance\secrets\claude_session_key.txt` (0600, and that
  `secrets/` directory sits **outside any git repo entirely** — not just
  gitignored — as defense in depth). `glance.yml` reads it via
  `${readFileFromEnv:CLAUDE_SESSION_KEY_FILE}`, never as a raw value in the
  YAML.
- Bind mounts: `config_dir` = `C:/Users/cafe/WSL/glance/config` (this repo's
  working copy), `editor_script_dir` = `C:/Users/cafe/WSL/glance/editor`
- Variables: `port` (`8080`), `editor_port` (`8081`),
  `editor_interface_alias` (`Tailscale`), `claude_session_key` *(sensitive)*
- Output: `url` = `http://localhost:8080`
- Ports published as plain `0.0.0.0:PORT` rather than bound to a specific
  Tailscale IP — Rancher Desktop's WSL port-forwarding doesn't reliably proxy
  binds to a non-loopback address (confirmed: connections silently reset).
  Real reachability scoping is the Windows Firewall rule
  (`GlanceConfigEditor-Tailscale`, scoped to the `Tailscale` interface) —
  **workflow going forward: edit `glance.yml` and/or `terraform.tfvars`, then
  `terraform apply -target=module.glance.terraform_data.glance` from
  `infra/self-hosted` (scoped on purpose — see the drift warning above and
  the tainted-resources list below for why a bare apply is unsafe right now)
  — do not hand-run `nerdctl run` directly, Terraform owns the container
  lifecycle.**
- **Home page Services widget grew 2026-08-02**, all as plain link tiles
  (not iframes, to sidestep the HTTPS/mixed-content issue described below) —
  Jellyfin, then a local LLM chat UI (`bourbon.tailf9e677.ts.net:8090`,
  llama-server's own built-in webui — see [[local-server-setup]]), then
  Odysseus itself (`bourbon.tailf9e677.ts.net:7000`). All three use
  BOURBON's Tailscale MagicDNS hostname rather than its raw Tailscale IP —
  still Tailscale-gated (public DNS can't resolve `.ts.net` names at all),
  just a friendlier address, per an explicit ask to prefer a domain name
  over the IP.

### `launcher` — desktop-app launcher

Not containerized (GUI apps can't launch from inside a container/WSL
sandbox) — a native PowerShell `System.Net.HttpListener` on port 8082 with a
hardcoded allowlist of app-name → `Start-Process` path+args. Rendered in
`glance.yml` as a `custom-api` widget with no `url` (static HTML, zero HTTP
calls) styled as a desktop icon grid.

- Setup requires a one-time elevated step: `netsh http add urlacl` so the
  listener can bind without running elevated, plus a firewall rule
  (`GlanceLauncher-Tailscale`) and an `AtLogOn` Scheduled Task
  (`GlanceLauncher`) to keep it running across reboots.
- Variables: `port` (`8082`), `interface_alias` (`Tailscale`), `script_dir`
  (`C:/Users/cafe/WSL/glance/launcher`), `task_name` (`GlanceLauncher`)
- Output: `port` = `8082`

### `jellyfin` — media server

Added 2026-08-02. Same `nerdctl` sidecar pattern as `glance`.

- Container: `docker.io/jellyfin/jellyfin`, port `8096`
- Volumes: `config`/`cache`/`media` under `C:\Users\cafe\WSL\jellyfin\` —
  `media` is left as an empty placeholder on purpose, no existing media
  location was assumed or searched for
- Variables: `port` (`8096`), `config_dir`, `cache_dir`, `media_dir`,
  `interface_alias` (`Tailscale`)
- Output: `url` = `http://localhost:8096`
- First-run account setup still needs to happen in a browser (confirmed via
  `StartupWizardCompleted:false` on the unauthenticated `/System/Info/Public`
  endpoint) — not something Terraform can do.

## Secrets

Three sensitive variables exist, none committed — set in a gitignored
`terraform.tfvars` (the tracked reference is `terraform.tfvars.example` with
`"CHANGEME"` placeholders):

| Variable | Used by |
|---|---|
| `pi4_ssh_password` | `thingsboard_pi4` (SSH auth to the pi4) |
| `thingsboard_postgres_password` | `thingsboard_pi4` (Postgres role password) |
| `claude_session_key` | `glance` (Claude Usage widget — full session cookie, not a scoped API key; leak = account compromise) |

State (`terraform.tfstate`) and `.tfvars` are both gitignored in `infra/`;
`.terraform.lock.hcl` is committed on purpose.

## What's NOT wired up yet (as of 2026-08-02)

- **Cloudflare Tunnel** (`bourbon-homelab`, native Windows service, exposes
  `https://homelab.mashallow.cloud`) is **not Terraform-managed** — routing
  and the Access "Kyle only" email-OTP policy live entirely in the Cloudflare
  Zero Trust dashboard. Only one route exists today:
  `homelab.mashallow.cloud` → `http://localhost:8080` (Glance itself). The
  config-editor and launcher are reachable only via their Tailscale IP over
  plain HTTP, not through the tunnel — path-based routes
  (`/editor*`, `/launcher*` on the same hostname) are planned but not done.
- **Pending manual (elevated) steps**, all previously handed to Kyle because
  UAC elevation reliably fails when triggered from an automated Terraform
  `local-exec` in this environment:
  - `Jellyfin-Tailscale` firewall rule (port 8096) — not yet created;
    `terraform_data.jellyfin_firewall` is tainted in state until it exists.
  - `module.glance.terraform_data.editor_firewall` and
    `module.launcher.terraform_data.privileged` are tainted;
    `module.launcher.terraform_data.task` is missing from state entirely —
    all residue from the same elevation limitation.
  - **New 2026-08-02:** Odysseus (see [[glance-dashboard]] /
    [[local-server-setup]]) got `APP_BIND=0.0.0.0` so its port 7000 is
    reachable outside NixOS-WSL, and a Services tile was added pointing at
    it — but WSL2's localhostForwarding only covers Windows' own
    `127.0.0.1`, not its Tailscale/LAN interfaces, so the tile won't
    actually connect until Kyle runs (not Terraform-managed at all, this is
    plain Windows networking, outside `infra/self-hosted` entirely):
    ```powershell
    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=7000 connectaddress=127.0.0.1 connectport=7000
    New-NetFirewallRule -DisplayName 'Odysseus-Tailscale' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 7000 -InterfaceAlias 'Tailscale'
    ```
- **`infra/self-hosted`'s own git history has not caught up to its working
  tree.** As of this writing, the `monitoring` module (schtasks health-probe
  → `out/llm-health.log` + ntfy alerts) has been **deleted** from the working
  tree but is still what the repo's `README.md` describes; conversely
  `thingsboard_pi4`, `glance`, `launcher`, and `jellyfin` all exist as
  **uncommitted** modules not mentioned in the README at all. Treat this
  document (and the actual `.tf` files) as more current than
  `infra/self-hosted/README.md` until that repo's history is reconciled.
- **LLM cutover** (pointing odysseus's `LLM_HOST` at a local LLM instead of
  the old GCP spot VM) is built and bench-verified but still awaiting
  sign-off — runbook at `infra\docs\cutover-runbook.md`. Re-confirmed
  2026-08-02: Kyle explicitly chose to leave Odysseus's `LLM_HOST` alone
  again this session, even while doing unrelated Odysseus work (fixing its
  startup, exposing its UI on the dashboard) — this is a live, repeatedly
  reaffirmed "not yet" rather than an oversight.

## Related context (not Terraform-managed)

- **llama.cpp** — now the sole LLM engine on this box (Ollama fully
  uninstalled 2026-08-02, see the drift warning above). Two independent
  instances: NixOS-WSL (CUDA) and native Windows (Vulkan). The native
  Windows one (`gemma4-12b`, port 8090) is the canonical always-on
  instance — Windows Startup autostart, `0.0.0.0` bind, reachable via LAN
  and Tailscale, and now what NixOS-WSL's own CLI tools (`pi`, `opencode`)
  point at too (their WSL-side `services.ollama` was removed in favor of a
  `llama-gemma4-config-sync` systemd unit that repoints them at the Windows
  instance — full detail in [[local-server-setup]]). None of this is under
  Terraform; it's plain installed binaries, a Windows Startup-folder script,
  and a NixOS `configuration.nix` systemd unit (a completely separate
  declarative-config system from `infra/self-hosted`'s Terraform).
- **GCP `llm-server`** — the VM this whole `compute`/`llm_server` pair
  was originally built to replace, back when Ollama was the plan. A
  hand-built spot VM, never itself in Terraform, stopped since 2026-07-18,
  no consumer pointed at it currently. Doubly moot now that Ollama itself is
  gone too — worth folding into whatever decision resolves the `compute`/
  `networking`/`llm_server` drift above.
