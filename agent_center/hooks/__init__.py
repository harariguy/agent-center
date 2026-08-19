"""Per-harness lifecycle hooks — served artifacts, one directory per harness.

Each subpackage holds the files an agent writes into its own harness so the
notify policy is *delivered* every session instead of depending on a skill-index
scan. The files are served with `{base}` templating by `..docs`, the same way
the skill is. `hermes/` is the first harness; others follow the same layout.
"""
