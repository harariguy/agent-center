# Security policy

## Supported versions

This is a hobby project. Only the latest release (and `main`) receive fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting ("Security" tab → "Report a
vulnerability") rather than a public issue, so a fix can land before the
details are public. Reports are handled on a best-effort basis — expect an
acknowledgement within a week.

## Deployment model, in one paragraph

Knowing the intended boundaries helps qualify a finding. Local mode binds to
loopback with no UI auth — the loopback bind *is* the boundary, and any process
on the machine can read the feed by design; a passwordless server additionally
refuses non-loopback peers per request. Hosted mode requires `ADMIN_PASSWORD`
(enforced at startup and per request), agent tokens gate every write, viewer
tokens are read/triage only and cannot manage agents, and TLS is delegated to
the platform or reverse proxy. Anything that crosses those lines — reading
without a credential on a hosted deploy, writing with a viewer token, escaping
the loopback guard, recovering a password from a cookie — is a vulnerability;
please report it.
