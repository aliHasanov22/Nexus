from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, STATIC_DIR, TEMPLATES_DIR
from .database import (
    activate_scenario,
    create_alert,
    create_user,
    delete_staff_account,
    get_active_incident,
    get_user_by_email,
    get_user_by_id,
    init_database,
    list_public_alerts,
    list_recent_incidents,
    list_staff_accounts,
    resolve_active_incidents,
    update_staff_account,
)
from .schemas import (
    AlertPayload,
    LoginPayload,
    RegisterPayload,
    ScenarioPayload,
    StaffCreatePayload,
    StaffUpdatePayload,
)
from .security import create_session_token, decode_session_token, hash_password, verify_password
from .simulation import (
    build_live_state,
    compute_delay_minutes,
    compute_evacuation_estimate,
    get_default_public_scenarios,
    get_network_definition,
    get_scenario_catalog,
)
from .seed_data import SCENARIOS


app = FastAPI(title="Nexus MetroTwin")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_database()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_payload(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "iat": _utc_now(),
    }


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "is_active": user["is_active"],
    }


def get_current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    session = decode_session_token(token)
    if not session or "sub" not in session:
        return None

    user = get_user_by_id(session["sub"])
    if user is None or not user["is_active"]:
        return None

    return user


def redirect_for_role(role: str) -> str:
    if role == "staff":
        return "/staff"
    if role == "admin":
        return "/admin"
    return "/user"


def require_roles(request: Request, allowed_roles: set[str]) -> dict[str, Any]:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if user["role"] not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return user


def page_guard(request: Request, allowed_roles: set[str], login_path: str = "/login") -> dict[str, Any] | RedirectResponse:
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(login_path, status_code=status.HTTP_303_SEE_OTHER)
    if user["role"] not in allowed_roles:
        return RedirectResponse(redirect_for_role(user["role"]), status_code=status.HTTP_303_SEE_OTHER)
    return user


def build_bootstrap_payload(user: dict[str, Any]) -> dict[str, Any]:
    alerts = list_public_alerts()
    incident = get_active_incident()
    return {
        "session": _public_user(user),
        "server_time": _utc_now(),
        "network": get_network_definition(),
        "scenarios": get_scenario_catalog(public_only=user["role"] == "user"),
        "public_preview_scenarios": get_default_public_scenarios(),
        "live_state": build_live_state(incident, alerts),
        "recent_incidents": list_recent_incidents(),
    }


@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "request": request,
            "current_user": _public_user(user) if user else None,
        },
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = get_current_user(request)
    if user:
        return RedirectResponse(redirect_for_role(user["role"]), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "auth.html",
        {"request": request, "mode": "login", "portal": "public", "current_user": None},
    )


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = get_current_user(request)
    if user:
        return RedirectResponse(redirect_for_role(user["role"]), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "auth.html",
        {"request": request, "mode": "register", "portal": "public", "current_user": None},
    )


@app.get("/staff-login", response_class=HTMLResponse)
def staff_login_page(request: Request) -> HTMLResponse | RedirectResponse:
    user = get_current_user(request)
    if user:
        return RedirectResponse(redirect_for_role(user["role"]), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "auth.html",
        {"request": request, "mode": "login", "portal": "staff", "current_user": None},
    )


@app.get("/user", response_class=HTMLResponse)
def user_dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    guarded = page_guard(request, {"user", "staff", "admin"})
    if isinstance(guarded, RedirectResponse):
        return guarded

    return templates.TemplateResponse(
        request,
        "dashboard_user.html",
        {"request": request, "current_user": _public_user(guarded)},
    )


@app.get("/staff", response_class=HTMLResponse)
def staff_dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    guarded = page_guard(request, {"staff", "admin"}, login_path="/staff-login")
    if isinstance(guarded, RedirectResponse):
        return guarded

    return templates.TemplateResponse(
        request,
        "dashboard_staff.html",
        {"request": request, "current_user": _public_user(guarded)},
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request) -> HTMLResponse | RedirectResponse:
    guarded = page_guard(request, {"admin"}, login_path="/staff-login")
    if isinstance(guarded, RedirectResponse):
        return guarded

    return templates.TemplateResponse(
        request,
        "dashboard_admin.html",
        {"request": request, "current_user": _public_user(guarded)},
    )


@app.get("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.post("/api/auth/register")
def register_account(payload: RegisterPayload) -> JSONResponse:
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists.")

    user = create_user(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="user",
    )

    response = JSONResponse({"redirect_to": redirect_for_role(user["role"]), "role": user["role"]})
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(_session_payload(user)),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/api/auth/login")
def login_account(payload: LoginPayload) -> JSONResponse:
    user = get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is currently disabled.")
    if payload.portal == "staff" and user["role"] not in {"staff", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff credentials are required for this portal.")

    response = JSONResponse({"redirect_to": redirect_for_role(user["role"]), "role": user["role"]})
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(_session_payload(user)),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/api/bootstrap")
def bootstrap(request: Request) -> dict[str, Any]:
    user = require_roles(request, {"user", "staff", "admin"})
    return build_bootstrap_payload(user)


@app.get("/api/live-state")
def live_state(request: Request) -> dict[str, Any]:
    require_roles(request, {"user", "staff", "admin"})
    return build_live_state(get_active_incident(), list_public_alerts())


@app.post("/api/staff/scenario")
def set_scenario(request: Request, payload: ScenarioPayload) -> dict[str, Any]:
    user = require_roles(request, {"staff", "admin"})
    if payload.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown scenario.")

    estimated_delay = compute_delay_minutes(
        payload.scenario_id,
        payload.affected_station_ids,
        payload.affected_segment_ids,
    )
    evacuation_estimate = compute_evacuation_estimate(payload.scenario_id, payload.affected_station_ids)

    activate_scenario(
        scenario_id=payload.scenario_id,
        label=SCENARIOS[payload.scenario_id]["label"],
        notes=payload.notes,
        affected_station_ids=payload.affected_station_ids,
        affected_segment_ids=payload.affected_segment_ids,
        created_by=user["email"],
        estimated_delay=estimated_delay,
        evacuation_estimate=evacuation_estimate,
    )

    return build_live_state(get_active_incident(), list_public_alerts())


@app.post("/api/staff/resolve")
def resolve_scenario(request: Request) -> dict[str, Any]:
    require_roles(request, {"staff", "admin"})
    resolve_active_incidents()
    return build_live_state(None, list_public_alerts())


@app.post("/api/alerts")
def publish_alert(request: Request, payload: AlertPayload) -> dict[str, Any]:
    user = require_roles(request, {"staff", "admin"})
    alert = create_alert(
        title=payload.title,
        message=payload.message,
        severity=payload.severity,
        created_by=user["email"],
    )
    return {"alert": alert, "live_state": build_live_state(get_active_incident(), list_public_alerts())}


@app.get("/api/admin/staff")
def admin_staff_list(request: Request) -> dict[str, Any]:
    require_roles(request, {"admin"})
    return {"staff_accounts": [_public_user(user) for user in list_staff_accounts()]}


@app.post("/api/admin/staff")
def admin_create_staff(request: Request, payload: StaffCreatePayload) -> dict[str, Any]:
    require_roles(request, {"admin"})
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email address is already in use.")

    user = create_user(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    return {"staff_account": _public_user(user)}


@app.patch("/api/admin/staff/{user_id}")
def admin_update_staff(user_id: str, request: Request, payload: StaffUpdatePayload) -> dict[str, Any]:
    current_user = require_roles(request, {"admin"})
    if current_user["id"] == user_id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own active admin session.")

    try:
        updated = update_staff_account(user_id, is_active=payload.is_active, role=payload.role)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff account not found.")
    return {"staff_account": _public_user(updated)}


@app.delete("/api/admin/staff/{user_id}")
def admin_delete_staff(user_id: str, request: Request) -> dict[str, Any]:
    current_user = require_roles(request, {"admin"})
    if current_user["id"] == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete the account you are using.")

    try:
        deleted = delete_staff_account(user_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff account not found.")
    return {"deleted": True}
