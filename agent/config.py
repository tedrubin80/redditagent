"""Configuration parsing without exposing credentials in representations."""
import os
from dataclasses import dataclass, field

@dataclass(frozen=True)
class RedditConfig:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    user_agent: str

    @classmethod
    def from_env(cls):
        names = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
        values = [os.environ.get(name, "").strip() for name in names]
        missing = [name for name, value in zip(names, values) if not value]
        if missing:
            raise ValueError("Missing configuration: " + ", ".join(missing))
        if "REPLACE_ME" in values[2]:
            raise ValueError("Set REDDIT_USER_AGENT to a descriptive identifier and your username")
        return cls(*values)
