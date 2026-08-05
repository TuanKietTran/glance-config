# Glance New Tab

Standalone browser extension that overrides the New Tab page with a
Glance-inspired dashboard: clock, weather, search, bookmarks, a VOZ RSS
tab group (with manual reload), Hacker News front page, and GitHub repo
stats. No server, no daemon, no `glance.yml` needed — every widget fetches
its data client-side, straight from the browser.

Data sources (all pull-only — none of these expose a push/SSE endpoint,
so widgets poll every 5 minutes and on tab focus rather than streaming):

- VOZ forum RSS feeds
- GitHub REST API (`api.github.com`)
- Hacker News via the Algolia API (`hn.algolia.com`)
- Open-Meteo for weather (`api.open-meteo.com`)

## Install (unpacked, Chrome/Brave)

1. Go to `brave://extensions` (or `chrome://extensions`).
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this folder.
4. Open a new tab.

For the browser's startup page too, set "On startup" to **Open the New
Tab page** rather than a specific URL — that way the extension handles
both cases and no URL is ever shown in the omnibox.
