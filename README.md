# glance-config

Glance configuration deployed to `pi3` (`https://pi3.tailf9e677.ts.net`).

## YAML modules

Optional pages live in `modules/*.yml`. Each module may provide metadata, a
`css_snippet`, and one or more `pages`. The module manager renders enabled
modules into `/opt/glance/glance.yml` from the tracked `glance.yml` base.

Open the dashboard's **Config** page to enable or disable modules without
editing YAML. The same UI retains a Monaco editor for the base configuration.
Changes are validated, written atomically, and applied by restarting Glance;
a failed restart restores the previous runtime config.

The manager listens only on `127.0.0.1:8081` and is exposed to the tailnet at
`/config/` through Tailscale Serve. Enabled state is stored on pi3 in
`/opt/glance/modules-enabled.json` and survives deployments.

## Deployment

A version tag (`YYYYMMDD-HHMM`) or manual workflow run copies the base config,
modules, module manager, and systemd unit to pi3. The deploy reconciles the
persisted enabled-module state before restarting Glance.
