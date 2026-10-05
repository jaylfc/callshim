"""Transforms: small, separately switchable rewrites of a model's tool calls (and of requests).

A call transform receives one tool call as {"id", "name", "arguments": dict} plus a Context, and returns
the call (rewritten or unchanged). Every change is reported with ctx.note(), which the proxy logs, so a
run can be audited and counted. A transform must only rewrite shapes it is sure about: when in doubt,
leave the call alone and let the harness report its own error.
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class Context:
    profile: dict
    tools: dict            # tool name -> JSON schema "parameters", from the request the harness sent
    state: "object"        # ebms.state.State: hash -> path map and the like, shared across requests
    notes: list = dataclasses.field(default_factory=list)

    def note(self, transform: str, before: object, after: object, detail: str = "") -> None:
        self.notes.append({"transform": transform, "detail": detail,
                           "before": str(before)[:400], "after": str(after)[:400]})

    def enabled(self, name: str) -> bool:
        return name in self.profile.get("transforms", [])


def call_transforms():
    from . import aliases, eval_browser, hashline
    # Order matters: names first (so later transforms see the harness's tool name), then payloads.
    return [("aliases", aliases.apply), ("hashline", hashline.apply), ("eval_browser", eval_browser.apply)]
