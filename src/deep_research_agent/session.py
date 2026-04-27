from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from uuid import uuid4


@dataclass(slots=True)
class SessionPaths:
    session_id: str
    session_dir: Path
    workspace_dir: Path
    logs_dir: Path
    metadata_path: Path


def create_session(base_dir: Path, *, user_input: str, session_id: str | None = None) -> SessionPaths:
    base_dir = Path(base_dir).resolve()
    resolved_session_id = session_id or _make_session_id(user_input)
    session_dir = base_dir / resolved_session_id
    workspace_dir = session_dir / "workspace"
    logs_dir = session_dir / "logs"
    metadata_path = session_dir / "session.json"

    workspace_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "session_id": resolved_session_id,
        "created_at": datetime.now(UTC).isoformat(),
        "user_input": user_input,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return SessionPaths(
        session_id=resolved_session_id,
        session_dir=session_dir,
        workspace_dir=workspace_dir,
        logs_dir=logs_dir,
        metadata_path=metadata_path,
    )


def _make_session_id(user_input: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = sha1(user_input.encode("utf-8")).hexdigest()[:8]
    return f"{timestamp}_{digest}_{uuid4().hex[:6]}"
