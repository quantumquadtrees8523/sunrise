---
name: custom-cards
description: Builds and changes the house's own dashboards from a library of custom Lovelace cards, keeping Home Assistant the engine and its stock dashboards untouched - checks the catalog first (an existing card, then a stock card restyled by the theme, then a new card), writes cards as presentation-only web components that take every entity from their config and handle every state, styles them from the house's design system, tests every state in stories, takes a checkpoint, deploys the bundle and dashboard config locally, verifies on a real device with read-back, and keeps the previous bundle and dashboard for undo. Use when someone asks for a dashboard, a panel or a card, "make my dashboard look like this", "add a card for the lights", or wants a card changed or put back.
---

# Custom cards

Read `references/HOUSE-BASICS.md` first. Done means the rubric in `references/RUBRIC.md` passes.

**Result:** the dashboard the owner asked for, in the house's look, seen working on a real
device in a real browser and read back from Home Assistant; the previous bundle and dashboard are
kept, and the owner knows how to undo it.

Home Assistant stays the engine. Dashboards stay Lovelace config. The look comes from a library
of custom Lovelace cards (Lit web components). Write dashboard config from the catalog; write
card code only when nothing in the catalog fits.

## Hard rules

- Catalog first. Before writing a card, check: (1) a custom card already in the library, (2) a
  stock card restyled by the theme, (3) a new card. Go to (3) only when (1) and (2) can't do it.
- Cards are presentation only. No house logic in a card: read from `hass.states`, act through
  `hass.callService`. Automations, scenes and scripts belong in Home Assistant (`routines`).
- No hard-coded entities. Every entity comes from the card's config (`setConfig`). A card must
  work in any house.
- Every card handles every state: on, off, `unavailable`, `unknown`, loading (no `hass` yet),
  and a missing entity (a clear inline message, never a blank or a thrown error).
- Readability over style. Body text is always readable. Style comes from color, shape and
  motion, never from degraded type.
- Local only. No CDN. Fonts and assets are bundled and served from Home Assistant itself.
- Accessible: keyboard reachable, visible focus, roles and labels, no meaning by color alone;
  respect the reduced-motion setting (prefers-reduced-motion).
- Never touch the stock Overview dashboard. Custom dashboards are separate dashboards.
- A card never locks, unlocks, opens or arms in one tap: it asks first. Never test on one.
- Never put a token in memory, a card, a story or a dashboard file, and never print one.

## Memory

Start: `memory_read` `house.md` (how the agent reaches `<config>`, the test device) and
`playbooks/dashboards.md` (library location, design system location, resource id, dashboard
slugs, card quirks); `owner.md` for how they like dashboards to look and behave.

Design system: its location is in `playbooks/dashboards.md`. If none is recorded, ask the owner
once where it is and record the answer. If there is none, use Home Assistant's theme variables.

End: phase 6.

## The card contract (Home Assistant's)

`setConfig`, `set hass` (re-render only when its own entities change), `getCardSize`,
`getGridOptions` (sections view), `static getStubConfig`, and a `window.customCards` entry so it
shows in the card picker. Add `getConfigElement` when the config is more than an entity.

Tokens, type and motion come from the design system. Expose tokens as CSS custom properties on
`:host`, falling back to Home Assistant's theme variables (`--primary-text-color` and so on) so
stock cards and these sit together. Light and dark both.

## Layout

```
<library>/
  src/
    tokens.css            # from the design system
    base.ts               # shared base card (hass diffing, state helpers, tokens)
    cards/<name>-card.ts  # one file per card
    index.ts              # imports every card, registers window.customCards
  stories/
    mock-hass.ts          # fake hass: states, callService (mutates state + logs), themes, user
    <name>-card.stories.ts
  dashboards/<slug>.json  # dashboard configs, source of truth
  scripts/deploy.sh
  vite.config.ts          # library build -> dist/<bundle>.js (single ES module)
  .storybook/             # framework: @storybook/web-components-vite
```

Create it the first time and record its location in memory. After that, keep to it. Installing its
build tools needs the internet once; offline, say so and use the catalog and stock cards.

## Phase 1: build a card

1. Confirm the catalog doesn't already cover it. A dashboard of existing cards skips to phase 2.
2. Write `src/cards/<name>-card.ts` on the shared base.
3. Write stories against the mock hass: every state above, light and dark, every supported size,
   and an interaction story that clicks it and checks `callService` was called with the right
   domain, service and entity.
4. Run `storybook build`, the story tests (Vitest addon) and the a11y addon. All must pass.
5. Look at it: screenshot the stories and check them by eye against the design system. No
   browser? Say the visual check was skipped.

Exit: every story passes and looks right.

## Phase 2: checkpoint

Before the first deploy ever, and before any deploy you can't put back in one step: `backup`
op=create and confirm it is listed.

## Phase 3: deploy

1. `vite build` -> the bundle.
2. `house_map`'s setup says the install type; `house.md` says how to reach `<config>`. If it
   doesn't, ask once and record it. Copy the bundle to `<config>/www/<library>/<bundle>.js`,
   keeping the previous one as `<bundle>.prev.js`.
3. Register the resource once as `/local/<library>/<bundle>.js?v=<build hash>`, type `module`
   (Settings, Dashboards, Resources, or WebSocket `lovelace/resources/create`). On every later
   deploy update `?v=` (`lovelace/resources/update`), or browsers keep the old bundle.
4. Dashboards: fetch and keep the current config first (`lovelace/config`) for undo, then save
   `dashboards/<slug>.json` with `lovelace/config/save` (`url_path: <slug>`). Storage mode keeps
   Home Assistant's own dashboard editor working.
5. WebSocket calls need an administrator's long-lived access token. Ask the owner for one; it
   stays in a file on the agent's machine outside any repository. Memory records only where it
   is. Never use another service's token.

## Phase 4: verify

Done means seen working on the real house:

1. Open the dashboard in a real browser, signed in, hard reload; check the new `?v=` loaded.
2. From the card, act on the test device named in `house.md`; read its state back with `house_map`,
   then put it back with `act` (`CHECKED`).
3. No console errors from the custom elements.

A failed check: fix and deploy again, or undo (phase 5). Never leave a dashboard that failed.

## Phase 5: undo

- Card bundle: copy `<bundle>.prev.js` back over the bundle and bump `?v=`.
- Dashboard: save the kept previous config with `lovelace/config/save`.
- Read back the same way as phase 4.
- Everything broken: the checkpoint, through `undo` (its last resort).

These are WebSocket and file changes, so they aren't in `changes`; keep what each undo needs.

## Phase 6: save what was learned

- `playbooks/dashboards.md`: config path, resource id, dashboard slugs, library location, design
  system location, card and device quirks, dated.
- `owner.md`: look and feel preferences that showed up. `log.md`: date, what changed, the check.
- Never a token or password: say where it is kept.

Then `log_run`.

## Hands off to / called from

House logic a card wanted: `routines`. A device the card can't reach: `device-diagnosis`.
Make a new kind of dashboard work repeatable: `build-a-skill`. Put it back: `undo`.
Called from `improve-home` when an idea is a dashboard.

## Report

A few lines: what changed, the dashboard's address, what was checked, how to undo it.
