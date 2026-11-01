"""Project monitoring settings loaded from a local JSON file."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MonitorSettings:
    project_name: str
    subreddits: tuple[str, ...]
    keywords: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()
    poll_limit: int = 25
    community_notes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "MonitorSettings":
        if not isinstance(raw, dict):
            raise ValueError("Settings file must contain a JSON object")
        project = str(raw.get("project_name", "")).strip()
        subreddits = _string_list(raw.get("subreddits"), "subreddits")
        keywords = _string_list(raw.get("keywords"), "keywords")
        excludes = _string_list(raw.get("exclude_terms", []), "exclude_terms", allow_empty=True)
        try:
            poll_limit = int(raw.get("poll_limit", 25))
        except (TypeError, ValueError) as exc:
            raise ValueError("poll_limit must be an integer") from exc
        if not project:
            raise ValueError("project_name is required")
        if not subreddits:
            raise ValueError("subreddits must list at least one community")
        if not keywords:
            raise ValueError("keywords must list at least one include term")
        if poll_limit < 1 or poll_limit > 100:
            raise ValueError("poll_limit must be between 1 and 100")
        notes_raw = raw.get("community_notes") or {}
        if not isinstance(notes_raw, dict):
            raise ValueError("community_notes must be an object")
        notes = {str(k).lower(): str(v) for k, v in notes_raw.items()}
        return cls(
            project_name=project,
            subreddits=tuple(s.lower().lstrip("r/") for s in subreddits),
            keywords=tuple(keywords),
            exclude_terms=tuple(excludes),
            poll_limit=poll_limit,
            community_notes=notes,
        )

    @classmethod
    def load(cls, path: str | Path) -> "MonitorSettings":
        settings_path = Path(path)
        if not settings_path.is_file():
            raise ValueError(
                f"Settings file not found: {settings_path}. "
                "Copy config/settings.example.json to data/settings.json and edit it."
            )
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in settings file: {exc}") from None
        return cls.from_dict(raw)

    def note_for(self, subreddit: str) -> str:
        return self.community_notes.get(subreddit.lower(), "")


def _string_list(value, field_name: str, allow_empty: bool = False) -> list[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    cleaned = [item.strip() for item in value if item.strip()]
    if not cleaned and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return cleaned
