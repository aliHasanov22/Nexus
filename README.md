# Nexus MetroTwin

Nexus MetroTwin is a Python-first hackathon MVP for simulating a simplified Baku Metro digital twin. It includes role-based authentication, a public passenger dashboard, a metro staff operations console, and an admin panel for managing staff accounts.

## What it includes

- Public user registration and login with email/password
- Staff-only and admin-only access control
- Interactive metro graph with animated train markers
- Station crowding states, arrival estimates, and public alerts
- Latest available station-entry baselines enriched from `opendata.az` with local caching and synthetic fallback
- Scenario controls for:
  - Normal operation
  - Rush hour overload
  - Large event surge
  - Electricity failure
  - Train breakdown
  - Track intrusion
  - Ventilation failure
- Bottleneck analysis, delay impact, and evacuation buildup estimates
- Admin tools to create, deactivate, and delete staff accounts

## Stack

- Backend: FastAPI
- Persistence: SQLite
- Real-world data enrichment: `opendata.az` metro station daily entry dataset
- Frontend: Jinja templates + vanilla JavaScript + custom CSS
- Auth: signed HTTP-only cookie sessions
- Seed data: `app/seed_data.py`

## Project structure

```text
app/
  main.py              FastAPI routes and page rendering
  database.py          SQLite setup, seed bootstrap, CRUD helpers
  security.py          Password hashing and session signing
  simulation.py        Metro network and scenario calculations
  seed_data.py         Stations, trains, scenarios, and demo users
  templates/           Landing page, auth, dashboards
  static/
    css/styles.css     App styling
    js/                Dashboard, auth, and admin browser logic
data/                  SQLite database file is created here at runtime
main.py                ASGI entry shim
requirements.txt
```

## Run locally

1. Create a virtual environment:

   ```powershell
   py -m venv .venv
   ```

2. Install dependencies:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

4. Open:

   ```text
   http://127.0.0.1:8000
   ```

The SQLite database is created and seeded automatically on first startup.
If the `opendata.az` dataset is reachable, the app also caches the latest station-entry snapshot locally and uses it to refine station demand baselines.

## Demo credentials

- Public user
  - Email: `commuter@nexusmetro.local`
  - Password: `Metro123!`
- Metro staff
  - Email: `staff.ops@nexusmetro.local`
  - Password: `Metro123!`
- Admin
  - Email: `admin@nexusmetro.local`
  - Password: `Admin123!`

## Notes

- Public users can self-register.
- Staff accounts cannot self-register and must be created by an admin.
- The metro network and demand patterns use synthetic data for demonstration, but the station naming and operational scenarios are designed to feel realistic in a Baku Metro context.
- When available, the app enriches station demand with the latest public daily station-entry data from `opendata.az` and falls back gracefully to synthetic baselines when the feed is unavailable.

## Verification completed

The app was verified locally with:

- Landing page, public login, staff login, and admin panel routes
- Public user registration
- Staff scenario activation and public alert publishing
- Admin create, deactivate, and delete staff account flows
