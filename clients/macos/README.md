# Agent Notifications for macOS

An optional menu bar client. The server does not need it and does not know about
it — this is one more reader of the same read API, alongside the web UI.

<!-- The bell sits in the menu bar; the panel opens beneath it. -->

## What it does

- Keeps the feed in your menu bar, with the unread count on the icon.
- Raises a system banner when something new arrives, and again when a grouped
  item fires after you'd already read it.
- Lets you triage without opening a browser: read, archive, snooze, mark all read.
- Clicking a notification opens the source app — Linear, GitHub, wherever the
  work actually lives. This is an index, not a destination.

## Install

Requires macOS 14+ and a Swift 6 toolchain. Xcode is *not* required; the Command
Line Tools are enough (`xcode-select --install`).

```sh
cd clients/macos
make install          # builds, installs to /Applications, launches
```

Then open **Settings** from the `⋯` menu in the panel and fill in:

- **Server URL** — the same address you open in a browser.
- **Viewer token** — mint one on the server host:

  ```sh
  agent-notifications viewer add "macbook"
  ```

  A viewer token is read + triage only. It cannot post notifications, and you can
  revoke it without disturbing any agent.

If you can't run the CLI on the server host, the admin password works instead —
but it is the credential that administers the server, so prefer a token.
Click **Apply & test** to switch the running client to the new connection.

### Scriptable install

Everything Settings collects can instead be seeded from the environment, which
makes the whole install one shell command — handy when a script or an agent is
doing the installing. At launch, `AN_URL`, `AN_VIEWER_TOKEN` and
`AN_ADMIN_PASSWORD` override whatever is stored *and are persisted* — the URL
to UserDefaults, the credential to the Keychain. One seeded launch configures
the app for good; every later launch reads the stored values and needs no
environment at all.

```sh
AN_URL="https://notifications.example.com" \
AN_VIEWER_TOKEN="<token from: agent-notifications viewer add macbook>" \
make run
```

`make run` executes the packaged binary in the foreground, so it inherits the
shell's environment. To seed an already-installed copy, invoke the binary
inside the bundle the same way:

```sh
AN_URL=… AN_VIEWER_TOKEN=… "/Applications/Agent Notifications.app/Contents/MacOS/AgentNotifications"
```

Setting `AN_VIEWER_TOKEN` selects token auth; setting only `AN_ADMIN_PASSWORD`
selects password auth (and persists the password to the Keychain — prefer a
token, for the reason above).

Other targets:

```sh
make run         # foreground, logs to the terminal
make open        # detached, without installing
make uninstall   # quit and remove from /Applications
make help
```

## Can't find the icon?

It's a menu bar *extra*, so macOS places it left of the system icons — on a
notched Mac that can be immediately right of the notch, not over by the clock.
If the menu bar is crowded, macOS can also hide extras under the notch; quit
another menu bar app or ⌘-drag to reorder.

## How it polls

`GET /api/v1/notifications/facets` carries an ETag over its whole payload and
the newest occurrence, so a poll that finds nothing new answers `304` with no
body. The feed itself is only refetched when that ETag moves — and the menu bar
count comes from the facets response, so the badge costs no feed fetch at all.
When it does move, the client follows the feed cursor until every item is loaded.

The interval is halved while the panel is open and tripled in Low Power Mode.
A failed poll never stops the loop: the gap doubles per miss toward a
two-minute cap and snaps back to the normal cadence on the first success.
Waking from sleep and opening the panel both poll immediately, so a restarted
server is picked up the moment you look. After three consecutive misses the
menu bar bell shows slashed and the panel says it's retrying.

Two things worth knowing if you change this code:

- **URLSession must not run its own cache.** With a `URLCache` installed it does
  its own conditional revalidation and hands back a synthesized `200`, so the
  manual `If-None-Match` never surfaces as a `304` and the optimisation silently
  does nothing. `APIClient` sets `urlCache = nil` for exactly this reason.
- **Timestamps come back timezone-naive** when the server runs on SQLite
  (`2026-08-05T19:05:50.569219`, no offset). Read literally they'd be treated as
  local time. `ServerDate.parse` pins them to UTC, matching
  `frontend/src/lib/time.ts`.

## Design

The panel is a card list, chosen over two alternatives that were built and
thrown away — a dense "ledger" of hairline rows, and a keyboard-driven triage
split. Cards won because this feed is read in glances of a few seconds: the body
text and the source both need to be visible without hovering or selecting, and
a notification is usually acted on (open the PR, open the ticket) rather than
scanned past. Density is the wrong optimisation when the list is short and each
row is a decision.

Priority shows as a coloured accent only while an item is unread, so a triaged
feed goes quiet instead of staying loud. Triage controls stay hidden until the
pointer is over a card, so a feed at rest is only content.

## Diagnostics

Quickest first stop — mirrors poll results to stderr:

```sh
AN_VERBOSE=1 make run
# poll: 200 changed — 4 items, 2 unread
# poll: 304 not modified
```

The same events go to unified logging. Note that `log show` hides info and debug
unless you ask for both explicitly, which makes an otherwise healthy app look
silent:

```sh
log stream --predicate 'subsystem == "ai.tydra.agent-notifications"' --level debug
log show --last 5m --predicate 'subsystem == "ai.tydra.agent-notifications"' --info --debug
```

## Layout

```
Sources/AgentNotifications/
  App.swift            MenuBarExtra + settings window + banner handling
  Store.swift          poll loop, notify-on-change, optimistic triage
  APIClient.swift      auth, ETag poll, feed, triage writes
  Models.swift         wire types + the naive-timestamp fix
  Preferences.swift    UserDefaults + SMAppService (launch at login)
  Keychain.swift       credential storage
  Notifier.swift       the only file that touches UNUserNotificationCenter
  Views/               design system, panel, card, settings
Scripts/
  package_app.sh       SwiftPM executable -> signed .app bundle
  make_icon.swift      renders AppIcon.icns from code
```

## Signing

Builds are ad-hoc signed, which is enough to run locally and to use the
Keychain. Both credentials keep the standard application-restricted ACL; an
ad-hoc rebuild may therefore require entering the credential again. **Launch at
login is unreliable without a real signature** — macOS
often refuses to register an ad-hoc bundle, and the toggle reports the error
rather than silently lying. For a distributable build, set a Developer ID:

```sh
CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" make package
```

and notarize the result.
