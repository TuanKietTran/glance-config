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

## Theme

Styled to match Glance's actual default theme, not just its layout — colors,
spacing, and typography are pulled straight from
[glanceapp/glance](https://github.com/glanceapp/glance)'s own
`static/css/*.css`:

- background/widget/border colors: `hsl(240, 8%, 9%/10%/13%)`
- accent/link color: `hsl(43, 50%, 70%)` (Glance's `--color-primary`)
- font: JetBrains Mono, the exact `.woff2` Glance bundles (`fonts/`,
  [OFL-1.1 licensed](https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt))
- widget cards: 5px radius, 1px border, flat offset "shelf" shadow
- group tabs: underline-on-active text tabs (Glance's `widget-group.css`),
  not pill buttons

## Install (unpacked, Chrome/Brave)

1. Go to `brave://extensions` (or `chrome://extensions`).
2. Enable **Developer mode**.
3. Click **Load unpacked** and select this folder.
4. Open a new tab.

For the browser's startup page too, set "On startup" to **Open the New
Tab page** rather than a specific URL — that way the extension handles
both cases and no URL is ever shown in the omnibox.
