# Agent Center — brand basics

Mark: one row pulled clear of the pile. The accent row is what needs you; the muted stack is everything else.

## Color
| Role | Light | Dark |
| --- | --- | --- |
| Accent | `#2F6BFF` | `#2F6BFF` |
| Ink | `#1D1D1F` | `#F5F5F7` |
| Surface | `#F5F5F7` | `#0B0B0C` |
| Muted stack | ink at 42% | ink at 50% |

Status colors stay as the app already ships them: red needs-you, orange urgent, green ok. They are UI states, not brand colors — never recolor the mark with them.

## Type
Archivo 600 for the wordmark, tracking `-0.02em`, sentence case: **Agent Center**. Never `agent-center-app`. Monospace (JetBrains Mono / Geist Mono / ui-monospace) for package names, commands and code only.

## Geometry
32-unit grid. Accent row `M4 6.5h20` at 3.6 stroke; stack rows `M10 14h18 / 20.5 / 27` at 3.2, round caps. Clear space on all sides = the height of one row gap (6 units / 20% of the mark). Minimum mark size 16px. Below 20px use `menubar-16.svg` (heavier strokes, no color).

## Files
All paths relative to `brand/`.

- [`assets/mark.svg`](assets/mark.svg) — color mark, light backgrounds
- [`assets/mark-white.svg`](assets/mark-white.svg) — color mark, dark backgrounds
- [`assets/mark-mono.svg`](assets/mark-mono.svg) — single color, inherits `currentColor`
- [`assets/favicon.svg`](assets/favicon.svg) — favicon with automatic dark mode
- [`assets/menubar-16.svg`](assets/menubar-16.svg) — macOS menu bar template image
- [`assets/lockup-horizontal.svg`](assets/lockup-horizontal.svg), [`assets/lockup-stacked.svg`](assets/lockup-stacked.svg)
- [`assets/avatar-dark.svg`](assets/avatar-dark.svg), [`assets/avatar-light.svg`](assets/avatar-light.svg) — 512 square (PNG exports alongside)
- [`assets/og-1280x640.png`](assets/og-1280x640.png) — GitHub social preview / OG image
- [`assets/x-header-1500x500.png`](assets/x-header-1500x500.png) — X profile header

See also [`README-snippet.md`](README-snippet.md) for a README hero block that uses the lockup.

## Don't
- Do not put the mark in a rounded container or add a gradient.
- Do not equalise the row weights — the contrast between accent row and stack is the whole idea.
- Do not use the mark as a bullet, spinner or loading indicator.
- Do not set the wordmark in mono or all caps.
