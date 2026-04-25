from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import DATA_DIR, DB_PATH
from .security import hash_password
from .seed_data import DEMO_USERS, STARTER_ALERTS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _loads_json(value: str) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _user_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def _alert_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "message": row["message"],
        "severity": row["severity"],
        "target_role": row["target_role"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def _incident_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "scenario_id": row["scenario_id"],
        "label": row["label"],
        "notes": row["notes"] or "",
        "affected_station_ids": _loads_json(row["affected_station_ids"]),
        "affected_segment_ids": _loads_json(row["affected_segment_ids"]),
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "estimated_delay": row["estimated_delay"],
        "evacuation_estimate": row["evacuation_estimate"],
    }


def init_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL,
                target_role TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                label TEXT NOT NULL,
                notes TEXT,
                affected_station_ids TEXT NOT NULL,
                affected_segment_ids TEXT NOT NULL,
                status TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                estimated_delay INTEGER NOT NULL,
                evacuation_estimate INTEGER NOT NULL
            );
            """
        )

        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            for seed in DEMO_USERS:
                connection.execute(
                    """
                    INSERT INTO users (id, name, email, password_hash, role, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        seed["name"],
                        seed["email"].lower(),
                        hash_password(seed["password"]),
                        seed["role"],
                        1 if seed["is_active"] else 0,
                        _utc_now(),
                    ),
                )

        alert_count = connection.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        if alert_count == 0:
            for alert in STARTER_ALERTS:
                connection.execute(
                    """
                    INSERT INTO alerts (id, title, message, severity, target_role, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        alert["title"],
                        alert["message"],
                        alert["severity"],
                        alert["target_role"],
                        alert["created_by"],
                        _utc_now(),
                    ),
                )

        connection.commit()


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE lower(email) = ?",
            (email.lower().strip(),),
        ).fetchone()
    return _user_from_row(row)


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_from_row(row)


def create_user(name: str, email: str, password_hash: str, role: str = "user") -> dict[str, Any]:
    user_id = uuid.uuid4().hex
    created_at = _utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, name, email, password_hash, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (user_id, name.strip(), email.lower().strip(), password_hash, role, created_at),
        )
        connection.commit()
    user = get_user_by_id(user_id)
    if user is None:
        raise RuntimeError("User creation failed.")
    return user


def list_staff_accounts() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM users
            WHERE role IN ('staff', 'admin')
            ORDER BY role DESC, created_at DESC
            """
        ).fetchall()
    return [user for row in rows if (user := _user_from_row(row))]


def count_admin_accounts() -> int:
    with get_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()[0]


def update_staff_account(user_id: str, is_active: bool | None = None, role: str | None = None) -> dict[str, Any] | None:
    user = get_user_by_id(user_id)
    if user is None or user["role"] not in {"staff", "admin"}:
        return None

    next_role = role or user["role"]
    next_active = user["is_active"] if is_active is None else is_active

    if user["role"] == "admin" and (not next_active or next_role != "admin") and count_admin_accounts() <= 1:
        raise ValueError("At least one active admin account must remain available.")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE users
            SET role = ?, is_active = ?
            WHERE id = ?
            """,
            (next_role, 1 if next_active else 0, user_id),
        )
        connection.commit()
    return get_user_by_id(user_id)


def delete_staff_account(user_id: str) -> bool:
    user = get_user_by_id(user_id)
    if user is None or user["role"] not in {"staff", "admin"}:
        return False

    if user["role"] == "admin" and count_admin_accounts() <= 1:
        raise ValueError("The final active admin account cannot be deleted.")

    with get_connection() as connection:
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.commit()
    return True


def list_public_alerts(limit: int = 8) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM alerts
            WHERE target_role = 'public'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_alert_from_row(row) for row in rows]


def create_alert(
    title: str,
    message: str,
    severity: str,
    created_by: str,
    target_role: str = "public",
) -> dict[str, Any]:
    alert_id = uuid.uuid4().hex
    created_at = _utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO alerts (id, title, message, severity, target_role, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (alert_id, title.strip(), message.strip(), severity, target_role, created_by, created_at),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    return _alert_from_row(row)


def get_active_incident() -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM incidents
            WHERE status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return _incident_from_row(row)


def list_recent_incidents(limit: int = 5) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM incidents
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    incidents = []
    for row in rows:
        incident = _incident_from_row(row)
        if incident:
            incidents.append(incident)
    return incidents



def resolve_active_incidents() -> None:
    with get_connection() as connection:
        connection.execute("UPDATE incidents SET status = 'resolved' WHERE status = 'active'")
        connection.commit()


def activate_scenario(
    scenario_id: str,
    label: str,
    notes: str,
    affected_station_ids: list[str],
    affected_segment_ids: list[str],
    created_by: str,
    estimated_delay: int,
    evacuation_estimate: int,
) -> dict[str, Any] | None:
    resolve_active_incidents()

    if scenario_id == "normal":
        return None

    incident_id = uuid.uuid4().hex
    created_at = _utc_now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                id,
                scenario_id,
                label,
                notes,
                affected_station_ids,
                affected_segment_ids,
                status,
                created_by,
                created_at,
                estimated_delay,
                evacuation_estimate
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                incident_id,
                scenario_id,
                label,
                notes.strip(),
                json.dumps(affected_station_ids),
                json.dumps(affected_segment_ids),
                created_by,
                created_at,
                estimated_delay,
                evacuation_estimate,
            ),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    return _incident_from_row(row)
