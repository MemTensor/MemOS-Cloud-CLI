"""Persistent, private state used to connect native hook events."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .agents import DEFAULT_HOOK_AGENT


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class HookTurnState:
    """Data persisted after UserPromptSubmit until Stop."""

    version: int
    agent: str
    session_key: str
    conversation_id: str
    prompt: str
    created_at: str
    host_turn_id: str | None = None
    workspace_path: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_key: str,
        conversation_id: str,
        prompt: str,
        agent: str = DEFAULT_HOOK_AGENT,
        host_turn_id: str | None = None,
        workspace_path: str | None = None,
        now: datetime | None = None,
    ) -> "HookTurnState":
        timestamp = now or _utc_now()
        return cls(
            version=1,
            agent=agent,
            session_key=session_key,
            conversation_id=conversation_id,
            prompt=prompt,
            created_at=timestamp.astimezone(timezone.utc).isoformat(),
            host_turn_id=host_turn_id,
            workspace_path=workspace_path,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HookTurnState":
        return cls(
            version=int(data.get("version", 1)),
            agent=str(data.get("agent", DEFAULT_HOOK_AGENT)),
            session_key=str(data["session_key"]),
            conversation_id=str(data["conversation_id"]),
            prompt=str(data["prompt"]),
            created_at=str(data["created_at"]),
            host_turn_id=data.get("host_turn_id"),
            workspace_path=data.get("workspace_path"),
        )


class HookStateStore:
    """Store session/turn state files with atomic, private writes."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        agent: str = DEFAULT_HOOK_AGENT,
        ttl_seconds: int = 24 * 60 * 60,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.agent = agent.strip().lower() or DEFAULT_HOOK_AGENT
        self.root = (root or (Path.home() / ".memos" / "hook-state" / self.agent)).expanduser()
        self.ttl_seconds = ttl_seconds
        self._now = now

    @staticmethod
    def storage_key(session_key: str, host_turn_id: str | None = None) -> str:
        """Build a stable key while retaining a session-only fallback."""
        if host_turn_id is None or not str(host_turn_id).strip():
            return session_key
        return f"{session_key}\x00{host_turn_id}"

    @classmethod
    def key_digest(cls, session_key: str, host_turn_id: str | None = None) -> str:
        return hashlib.sha256(cls.storage_key(session_key, host_turn_id).encode("utf-8")).hexdigest()

    def path_for(self, session_key: str, host_turn_id: str | None = None) -> Path:
        return self.root / f"{self.key_digest(session_key, host_turn_id)}.json"

    @staticmethod
    def _is_managed_path(path: Path) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{64}\.json", path.name))

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    def save(self, state: HookTurnState) -> Path:
        self._ensure_root()
        destination = self.path_for(state.session_key, state.host_turn_id)
        fd, temporary_name = tempfile.mkstemp(prefix=".turn-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(state), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, destination)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        return destination

    def load(self, session_key: str, host_turn_id: str | None = None) -> HookTurnState | None:
        self.cleanup()
        path = self.path_for(session_key, host_turn_id)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("state is not an object")
            state = HookTurnState.from_dict(data)
            if state.session_key != session_key:
                return None
            return state
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def consume(self, session_key: str, host_turn_id: str | None = None) -> HookTurnState | None:
        """Atomically claim and remove one pending turn state.

        Multiple host surfaces can report the same completed turn at nearly
        the same time (for example Cline's AgentPlugin and its IDE
        ``TaskComplete`` file hook).  A read followed by a later delete lets
        both processes observe the same state and both call ``memos add``.
        Renaming the state file first makes the claim atomic: only one
        process can move it out of the pending namespace.
        """
        self.cleanup()
        path = self.path_for(session_key, host_turn_id)
        temporary_name: str | None = None
        try:
            fd, temporary_name = tempfile.mkstemp(prefix=".consumed-", suffix=".json", dir=self.root)
            os.close(fd)
            os.unlink(temporary_name)
            os.replace(path, temporary_name)
            with open(temporary_name, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return None
            state = HookTurnState.from_dict(data)
            if state.session_key != session_key:
                return None
            return state
        except (FileNotFoundError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def delete(self, session_key: str, host_turn_id: str | None = None) -> bool:
        try:
            self.path_for(session_key, host_turn_id).unlink()
            return True
        except FileNotFoundError:
            return False

    def cleanup(self) -> int:
        if not self.root.exists():
            return 0
        removed = 0
        cutoff = self._now() - timedelta(seconds=self.ttl_seconds)
        for path in self.root.glob("*.json"):
            if not self._is_managed_path(path):
                continue
            expired = False
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                created = _parse_timestamp(data.get("created_at")) if isinstance(data, dict) else None
                expired = created is None or created < cutoff
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                expired = True
            if expired:
                try:
                    path.unlink()
                    removed += 1
                except FileNotFoundError:
                    pass
        return removed

    def clear(self) -> int:
        """Remove only state files managed by this store."""
        if not self.root.exists():
            return 0
        removed = 0
        for path in self.root.glob("*.json"):
            if not self._is_managed_path(path):
                continue
            try:
                path.unlink()
                removed += 1
            except FileNotFoundError:
                pass
        try:
            self.root.rmdir()
        except OSError:
            pass
        return removed
