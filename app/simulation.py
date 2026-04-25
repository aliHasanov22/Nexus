from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .opendata import get_latest_station_entries
from .seed_data import DEFAULT_EVENT_STATIONS, LINES, SCENARIOS, SEGMENTS, STATIONS, TRAINS


SEGMENT_LOOKUP = {segment["id"]: segment for segment in SEGMENTS}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_station_catalog() -> dict[str, Any]:
    data_feed = get_latest_station_entries()
    station_entries = data_feed.get("station_entries", {})
    enriched_stations = []

    for station in STATIONS:
        live_entry = station_entries.get(station["id"])
        effective_base = station["base_passengers"]
        daily_entries = None
        observed_date = None
        source_label = "Synthetic demo baseline"

        if live_entry:
            daily_entries = int(live_entry["daily_entries"])
            observed_date = data_feed.get("latest_date")
            source_label = "Latest station-entry baseline from opendata.az"
            effective_base = max(
                180,
                min(
                    station["max_capacity"] - 60,
                    int(round(daily_entries / 60)),
                ),
            )

        enriched_stations.append(
            {
                **station,
                "synthetic_base_passengers": station["base_passengers"],
                "base_passengers": effective_base,
                "daily_entries": daily_entries,
                "observed_date": observed_date,
                "data_source": data_feed.get("source", "seed") if live_entry else "seed",
                "source_label": source_label,
            }
        )

    return {
        "stations": enriched_stations,
        "data_feed": {
            "source": data_feed.get("source", "seed"),
            "latest_date": data_feed.get("latest_date"),
            "package_modified": data_feed.get("package_modified"),
            "cache_status": data_feed.get("cache_status", "unavailable"),
        },
    }


def _station_lookup() -> dict[str, Any]:
    return {station["id"]: station for station in get_station_catalog()["stations"]}


def get_network_definition() -> dict[str, Any]:
    station_bundle = get_station_catalog()
    return {
        "lines": list(LINES.values()),
        "stations": station_bundle["stations"],
        "segments": SEGMENTS,
        "trains": TRAINS,
        "data_feed": station_bundle["data_feed"],
    }


def get_scenario_catalog(public_only: bool = False) -> list[dict[str, Any]]:
    scenarios = list(SCENARIOS.values())
    if public_only:
        scenarios = [scenario for scenario in scenarios if scenario["public_enabled"]]
    return scenarios


def get_default_public_scenarios() -> list[str]:
    return ["normal", "rush-hour", "event-surge"]


def crowd_level_for_ratio(ratio: float) -> str:
    if ratio < 0.35:
        return "Low"
    if ratio < 0.6:
        return "Medium"
    if ratio < 0.82:
        return "High"
    return "Critical"


def _segment_label(segment_id: str) -> str:
    stations = _station_lookup()
    segment = SEGMENT_LOOKUP.get(segment_id)
    if not segment:
        return segment_id
    station_a = stations[segment["from"]]["name"]
    station_b = stations[segment["to"]]["name"]
    return f"{station_a} - {station_b}"


def _station_multiplier(station: dict[str, Any], scenario: dict[str, Any], affected_station_ids: set[str]) -> tuple[float, float]:
    multiplier = scenario["station_multiplier"]
    tags = set(station["tags"])

    if "hub" in tags:
        multiplier *= scenario["hub_multiplier"]
    if "transfer" in tags:
        multiplier *= scenario["transfer_multiplier"]
    if station["id"] in scenario["event_station_ids"]:
        multiplier *= scenario["event_multiplier"]
    if station["id"] in affected_station_ids:
        multiplier *= scenario["affected_station_multiplier"]

    capacity_factor = scenario["capacity_factor"]
    if scenario["id"] != "ventilation-failure" or station["id"] not in affected_station_ids:
        capacity_factor = 1.0

    return multiplier, capacity_factor


def get_station_projection(
    station: dict[str, Any],
    scenario_id: str,
    affected_station_ids: set[str] | None = None,
) -> dict[str, Any]:
    affected_station_ids = affected_station_ids or set()
    scenario = SCENARIOS[scenario_id]
    multiplier, capacity_factor = _station_multiplier(station, scenario, affected_station_ids)
    projected_capacity = max(1, int(station["max_capacity"] * capacity_factor))
    projected_passengers = int(station["base_passengers"] * multiplier)
    ratio = projected_passengers / projected_capacity
    crowd_level = crowd_level_for_ratio(ratio)

    status = "normal"
    if scenario_id == "track-intrusion" and station["id"] in affected_station_ids:
        status = "closed"
    elif scenario_id in {"electricity-failure", "ventilation-failure"} and station["id"] in affected_station_ids:
        status = "emergency"
    elif ratio >= 0.65:
        status = "crowded"

    return {
        "id": station["id"],
        "name": station["name"],
        "line": station["line"],
        "projected_passengers": projected_passengers,
        "projected_capacity": projected_capacity,
        "utilization": round(ratio, 3),
        "crowd_level": crowd_level,
        "status": status,
    }


def compute_delay_minutes(
    scenario_id: str,
    affected_station_ids: list[str],
    affected_segment_ids: list[str],
) -> int:
    scenario = SCENARIOS[scenario_id]
    return (
        scenario["delay_minutes"]
        + (len(affected_station_ids) * 3)
        + (len(affected_segment_ids) * 5)
    )


def compute_evacuation_estimate(scenario_id: str, affected_station_ids: list[str]) -> int:
    if scenario_id in {"normal", "rush-hour", "event-surge"}:
        return 0

    stations = _station_lookup()
    base = 90
    if scenario_id == "track-intrusion":
        base = 180
    elif scenario_id == "electricity-failure":
        base = 220
    elif scenario_id == "ventilation-failure":
        base = 140

    station_load = sum(
        stations[station_id]["base_passengers"]
        for station_id in affected_station_ids
        if station_id in stations
    )
    return base + int(station_load * 0.4)


def build_bottleneck_analysis(
    scenario_id: str,
    affected_station_ids: list[str],
) -> list[dict[str, Any]]:
    affected_set = set(affected_station_ids)
    station_catalog = get_station_catalog()["stations"]
    ranked = [
        get_station_projection(station, scenario_id, affected_set)
        for station in station_catalog
    ]
    ranked.sort(key=lambda item: item["utilization"], reverse=True)
    return ranked[:6]


def build_recommended_actions(
    scenario_id: str,
    affected_station_ids: list[str],
    affected_segment_ids: list[str],
) -> list[str]:
    stations = _station_lookup()
    station_names = [stations[station_id]["name"] for station_id in affected_station_ids if station_id in stations]
    segment_names = [_segment_label(segment_id) for segment_id in affected_segment_ids]

    if scenario_id == "normal":
        return [
            "Maintain normal dispatch spacing and keep live crowd monitors active.",
            "Use the public dashboard for passenger confidence messaging during demo mode.",
        ]
    if scenario_id == "rush-hour":
        return [
            "Stage platform marshals at 28 May, Cəfər Cabbarlı, and Memar Əcəmi.",
            "Increase dwell supervision and meter gate inflow at transfer stations.",
        ]
    if scenario_id == "event-surge":
        focus = ", ".join(station_names or [stations[station_id]["name"] for station_id in DEFAULT_EVENT_STATIONS[:3]])
        return [
            f"Pre-position queue barriers and wayfinding staff near {focus}.",
            "Broadcast staggered exit guidance before and after the event peak.",
        ]
    if scenario_id == "electricity-failure":
        focus = ", ".join(segment_names or ["the affected traction segment"])
        return [
            f"Isolate {focus}, hold trains short of the outage, and switch passengers to alternate transfer paths.",
            "Push immediate reroute messaging and prepare bus bridge escalation if recovery exceeds 20 minutes.",
        ]
    if scenario_id == "train-breakdown":
        return [
            "Hold following services to preserve headway and dispatch a response crew to the failed train.",
            "Use platform flow control on adjacent stations to limit unsafe buildup.",
        ]
    if scenario_id == "track-intrusion":
        focus = ", ".join(station_names or ["the incident station"])
        return [
            f"Close access near {focus}, suspend nearby movements, and route passengers through alternate stations.",
            "Trigger emergency announcements and coordinate with station security teams.",
        ]
    if scenario_id == "ventilation-failure":
        focus = ", ".join(station_names or ["the affected station"])
        return [
            f"Restrict entry at {focus} and meter exits while ventilation is restored.",
            "Open auxiliary ventilation where possible and prepare controlled evacuation if air quality drops further.",
        ]
    return []


def build_delay_matrix() -> list[dict[str, Any]]:
    matrix = []
    for scenario in SCENARIOS.values():
        matrix.append(
            {
                "id": scenario["id"],
                "label": scenario["label"],
                "delay_minutes": scenario["delay_minutes"],
                "severity": scenario["severity"],
            }
        )
    return matrix


def build_live_state(
    active_incident: dict[str, Any] | None,
    alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    stations = _station_lookup()
    scenario_id = active_incident["scenario_id"] if active_incident else "normal"
    scenario = SCENARIOS[scenario_id]
    affected_station_ids = active_incident["affected_station_ids"] if active_incident else []
    affected_segment_ids = active_incident["affected_segment_ids"] if active_incident else []
    delay_minutes = active_incident["estimated_delay"] if active_incident else compute_delay_minutes(scenario_id, [], [])
    evacuation_estimate = active_incident["evacuation_estimate"] if active_incident else 0

    return {
        "generated_at": _utc_now(),
        "scenario": scenario,
        "incident": active_incident,
        "alerts": alerts,
        "affected_stations": [
            {"id": station_id, "name": stations[station_id]["name"]}
            for station_id in affected_station_ids
            if station_id in stations
        ],
        "affected_segments": [
            {"id": segment_id, "label": _segment_label(segment_id)}
            for segment_id in affected_segment_ids
            if segment_id in SEGMENT_LOOKUP
        ],
        "delay_minutes": delay_minutes,
        "evacuation_estimate": evacuation_estimate,
        "bottlenecks": build_bottleneck_analysis(scenario_id, affected_station_ids),
        "recommended_actions": build_recommended_actions(
            scenario_id,
            affected_station_ids,
            affected_segment_ids,
        ),
        "delay_matrix": build_delay_matrix(),
    }
