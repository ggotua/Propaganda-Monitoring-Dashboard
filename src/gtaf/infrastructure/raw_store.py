"""Immutable raw caption store (SPEC-002 §3.4).

Raw payloads are the irreplaceable artefact: if a caption track changes or disappears on YouTube,
this file is the only copy. Therefore a file is created **exclusively** — never opened for writing
over an existing one. ``Path.open("x")`` is the OS-level guarantee that "write once" means once.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path


class FileRawStore:
    """Stores original ``json3`` payloads under ``<root>/<channel>/<date>/<video_id>.json3``."""

    def __init__(self, root: Path) -> None:
        """Initialise the store.

        Args:
            root: Directory for raw files, normally ``data/raw``.
        """
        self._root = root

    def path_for(self, channel_id: str, local_date: date, video_id: str) -> Path:
        """Return the canonical path for one payload.

        Args:
            channel_id: Owning channel slug.
            local_date: Broadcast date in Tbilisi local time.
            video_id: YouTube video id.

        Returns:
            The path, whether or not the file exists.
        """
        return self._root / channel_id / local_date.isoformat() / f"{video_id}.json3"

    def write_once(
        self, channel_id: str, local_date: date, video_id: str, payload: str
    ) -> bool:
        """Create the payload file if and only if it does not exist.

        Args:
            channel_id: Owning channel slug.
            local_date: Broadcast date in Tbilisi local time.
            video_id: YouTube video id.
            payload: Raw ``json3`` text.

        Returns:
            True when the file was created, False when it already existed and was left untouched.
        """
        path = self.path_for(channel_id, local_date, video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(payload)
        except FileExistsError:
            return False
        return True
