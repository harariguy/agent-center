"""Remote MCP surface — the portable way for any agent harness to notify.

`server` holds the JSON-RPC endpoint, `tools` the tool contract. The usage rules
and the installable skill live in `..docs`, shared with every other channel.
"""

from .server import router

__all__ = ["router"]
