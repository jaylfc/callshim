"""State the proxy keeps between requests.

- originals: tool-call id -> the call exactly as the model wrote it. Later requests get the original back in
  their history, so the model always sees its own tokens and the server's prompt cache stays a prefix match.
- hash_paths: hashline tag -> file path, learned from tool results ("[path#HASH]" headers), so an edit that
  names only "[HASH]" can be completed.
"""
from __future__ import annotations

import json
import pathlib
import re
import threading

HEADER = re.compile(r"\[([^\]\s#]+)#([0-9A-Fa-f]{3,8})\]")


class State:
    def __init__(self, path: pathlib.Path | None):
        self.path = path
        self.lock = threading.Lock()
        self.originals: dict[str, dict] = {}
        self.hash_paths: dict[str, str] = {}
        if path and path.exists():
            data = json.loads(path.read_text())
            self.originals = data.get("originals", {})
            self.hash_paths = data.get("hash_paths", {})

    def save(self) -> None:
        if not self.path:
            return
        with self.lock:
            # Bounded: the newest 2000 originals and 4000 tags are plenty for one long session.
            originals = dict(list(self.originals.items())[-2000:])
            hashes = dict(list(self.hash_paths.items())[-4000:])
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"originals": originals, "hash_paths": hashes}))
            tmp.replace(self.path)

    def learn_hashes(self, text: str) -> None:
        for path, tag in HEADER.findall(text or ""):
            self.hash_paths[tag.upper()] = path
