document.addEventListener("DOMContentLoaded", function () {
  if (document.body.dataset.page !== "dashboard" || !window.NexusCore) {
    return;
  }

  var role = document.body.dataset.dashboardRole || "user";
  var core = window.NexusCore;

  var state = {
    role: role,
    bootstrap: null,
    liveState: null,
    scenarioLookup: {},
    previewScenarioId: "live",
    selectedStationId: "may28",
    tick: 0,
    timers: [],
  };

  var elements = {
    summaryMetrics: core.byId("summary-metrics"),
    alertBanner: core.byId("alert-banner"),
    modeSummary: core.byId("dashboard-mode-summary"),
    map: core.byId("metro-map"),
    mapLegend: core.byId("map-legend"),
    previewControls: core.byId("public-preview-controls"),
    stationInspector: core.byId("station-inspector"),
    liveSituation: core.byId("live-situation"),
    passengerChart: core.byId("passenger-chart"),
    congestionChart: core.byId("congestion-chart"),
    delayChart: core.byId("delay-chart"),
    recommendedActions: core.byId("recommended-actions"),
    bottleneckList: core.byId("bottleneck-list"),
    stationCards: core.byId("station-cards"),
    scenarioForm: core.byId("scenario-form"),
    scenarioSelect: core.byId("scenario-select"),
    stationCheckboxes: core.byId("station-checkboxes"),
    segmentCheckboxes: core.byId("segment-checkboxes"),
    scenarioMessage: core.byId("scenario-message"),
    resetScenarioButton: core.byId("reset-scenario"),
    alertForm: core.byId("alert-form"),
    alertMessage: core.byId("alert-message"),
  };

  function asLookup(items) {
    var lookup = {};
    items.forEach(function (item) {
      lookup[item.id] = item;
    });
    return lookup;
  }

  function activeScenarioId() {
    if (state.role === "user" && state.previewScenarioId !== "live") {
      return state.previewScenarioId;
    }
    return state.liveState.scenario.id;
  }

  function activeScenario() {
    return state.scenarioLookup[activeScenarioId()] || state.liveState.scenario;
  }

  function activeIncident() {
    return state.previewScenarioId === "live" ? state.liveState.incident : null;
  }

  function affectedStationIds() {
    var incident = activeIncident();
    return incident ? incident.affected_station_ids || [] : [];
  }

  function affectedSegmentIds() {
    var incident = activeIncident();
    return incident ? incident.affected_segment_ids || [] : [];
  }

  function stationProjection(station) {
    var scenario = activeScenario();
    var affectedStations = new Set(affectedStationIds());
    var multiplier = scenario.station_multiplier;
    var tags = new Set(station.tags || []);

    if (tags.has("hub")) {
      multiplier *= scenario.hub_multiplier;
    }
    if (tags.has("transfer")) {
      multiplier *= scenario.transfer_multiplier;
    }
    if ((scenario.event_station_ids || []).includes(station.id)) {
      multiplier *= scenario.event_multiplier;
    }
    if (affectedStations.has(station.id)) {
      multiplier *= scenario.affected_station_multiplier;
    }

    var capacity = station.max_capacity;
    if (scenario.id === "ventilation-failure" && affectedStations.has(station.id)) {
      capacity = Math.max(1, Math.round(capacity * scenario.capacity_factor));
    }

    var wave = 0.96 + Math.sin((state.tick / 3) + station.x / 120) * 0.08;
    var projectedPassengers = Math.max(0, Math.round(station.base_passengers * multiplier * wave));
    var utilization = projectedPassengers / Math.max(capacity, 1);
    var crowdLevel = "Low";
    if (utilization >= 0.82) {
      crowdLevel = "Critical";
    } else if (utilization >= 0.6) {
      crowdLevel = "High";
    } else if (utilization >= 0.35) {
      crowdLevel = "Medium";
    }

    var status = "normal";
    if (scenario.id === "track-intrusion" && affectedStations.has(station.id)) {
      status = "closed";
    } else if (
      (scenario.id === "electricity-failure" || scenario.id === "ventilation-failure") &&
      affectedStations.has(station.id)
    ) {
      status = "emergency";
    } else if (utilization >= 0.65) {
      status = "crowded";
    }

    return {
      id: station.id,
      name: station.name,
      line: station.line,
      x: station.x,
      y: station.y,
      projectedPassengers: projectedPassengers,
      projectedCapacity: capacity,
      utilization: utilization,
      crowdLevel: crowdLevel,
      status: status,
      tags: station.tags,
    };
  }

  function buildTrainPath(route) {
    return route.concat(route.slice(0, -1).reverse());
  }

  function findSegmentId(fromId, toId) {
    var segments = state.bootstrap.network.segments;
    var match = segments.find(function (segment) {
      return (
        (segment.from === fromId && segment.to === toId) ||
        (segment.from === toId && segment.to === fromId)
      );
    });
    return match ? match.id : null;
  }

  function brokenTrainId() {
    var incident = activeIncident();
    if (!incident || state.liveState.scenario.id !== "train-breakdown") {
      return null;
    }

    var candidate = state.bootstrap.network.trains.find(function (train) {
      return incident.affected_station_ids.some(function (stationId) {
        return train.route.includes(stationId);
      });
    });

    if (!candidate) {
      candidate = state.bootstrap.network.trains.find(function (train) {
        return incident.affected_segment_ids.some(function (segmentId) {
          return train.route.some(function (stationId, index) {
            if (index === train.route.length - 1) {
              return false;
            }
            return findSegmentId(stationId, train.route[index + 1]) === segmentId;
          });
        });
      });
    }

    return candidate ? candidate.id : state.bootstrap.network.trains[0].id;
  }

  function simulateTrains() {
    var stationsById = asLookup(state.bootstrap.network.stations);
    var scenario = activeScenario();
    var affectedSegments = new Set(affectedSegmentIds());
    var affectedStations = new Set(affectedStationIds());
    var lockedTrain = brokenTrainId();
    var simClock = (Date.now() / 1000) * 2.15 + state.tick;

    return state.bootstrap.network.trains.map(function (train) {
      var path = buildTrainPath(train.route);
      var edgeCount = Math.max(1, path.length - 1);
      var travelDuration = 18 / Math.max(0.18, scenario.speed_factor * train.speed);
      var dwellDuration = 4.3 * scenario.dwell_factor;
      var cycleDuration = edgeCount * (travelDuration + dwellDuration);
      var phase = (simClock + (train.offset * cycleDuration)) % cycleDuration;

      var currentStation = path[0];
      var nextStation = path[1] || path[0];
      var x = stationsById[currentStation].x;
      var y = stationsById[currentStation].y;
      var progress = 0;
      var segmentId = findSegmentId(currentStation, nextStation);
      var edgeIndex = 0;
      var status = scenario.speed_factor < 0.94 ? "delayed" : "moving";
      var direction = "outbound";

      for (var index = 0; index < edgeCount; index += 1) {
        if (phase <= dwellDuration) {
          currentStation = path[index];
          nextStation = path[index + 1] || path[index];
          edgeIndex = index;
          x = stationsById[currentStation].x;
          y = stationsById[currentStation].y;
          progress = 0;
          segmentId = findSegmentId(currentStation, nextStation);
          status = "stopped";
          break;
        }

        phase -= dwellDuration;
        if (phase <= travelDuration) {
          currentStation = path[index];
          nextStation = path[index + 1] || path[index];
          edgeIndex = index;
          progress = phase / travelDuration;
          segmentId = findSegmentId(currentStation, nextStation);
          x =
            stationsById[currentStation].x +
            (stationsById[nextStation].x - stationsById[currentStation].x) * progress;
          y =
            stationsById[currentStation].y +
            (stationsById[nextStation].y - stationsById[currentStation].y) * progress;
          break;
        }

        phase -= travelDuration;
      }

      if (path.indexOf(nextStation) < path.indexOf(currentStation)) {
        direction = "inbound";
      }

      if (scenario.id === "train-breakdown" && train.id === lockedTrain) {
        status = "broken";
        progress = 0;
        x = stationsById[currentStation].x;
        y = stationsById[currentStation].y;
      } else if (
        (scenario.id === "electricity-failure" || scenario.id === "track-intrusion") &&
        (affectedSegments.has(segmentId) || affectedStations.has(currentStation) || affectedStations.has(nextStation))
      ) {
        status = "stopped";
        progress = 0.08;
      }

      return {
        id: train.id,
        line: train.line,
        currentStation: currentStation,
        nextStation: nextStation,
        direction: direction,
        speed: Math.round(scenario.speed_factor * train.speed * 100) / 100,
        passengerLoad: Math.round(train.base_load * (1 + (1 - scenario.speed_factor) * 0.6)),
        status: status,
        x: x,
        y: y,
        progress: progress,
        pathProgress: edgeIndex + progress,
        routePath: path,
        segmentId: segmentId,
      };
    });
  }

  function estimateArrival(stationId, stationLine, trains) {
    var bestMinutes = Number.POSITIVE_INFINITY;

    trains.forEach(function (train) {
      if (train.line !== stationLine || train.status === "broken") {
        return;
      }

      if (train.currentStation === stationId && train.status === "stopped") {
        bestMinutes = Math.min(bestMinutes, 0.4);
        return;
      }

      train.routePath.forEach(function (routeStationId, index) {
        if (routeStationId !== stationId) {
          return;
        }
        var distance = index - train.pathProgress;
        if (distance < 0) {
          distance += train.routePath.length - 1;
        }
        bestMinutes = Math.min(bestMinutes, distance * 1.4);
      });
    });

    if (!Number.isFinite(bestMinutes)) {
      return "6 min";
    }
    if (bestMinutes < 0.75) {
      return "Boarding";
    }
    return Math.max(1, Math.round(bestMinutes)) + " min";
  }

  function buildSimulation() {
    var stations = state.bootstrap.network.stations.map(stationProjection);
    var trains = simulateTrains();
    var orderedStations = stations
      .slice()
      .sort(function (left, right) {
        return right.utilization - left.utilization;
      })
      .map(function (station) {
        return Object.assign({}, station, {
          nextTrain: estimateArrival(station.id, station.line, trains),
        });
      });

    var totalPassengers = orderedStations.reduce(function (sum, station) {
      return sum + station.projectedPassengers;
    }, 0);

    var criticalCount = orderedStations.filter(function (station) {
      return station.crowdLevel === "Critical" || station.status === "closed";
    }).length;

    var onTimeRate = Math.max(
      42,
      Math.round((1 - (state.liveState.delay_minutes / 60)) * 100)
    );

    return {
      stations: orderedStations,
      stationsById: asLookup(orderedStations),
      trains: trains,
      totalPassengers: totalPassengers,
      criticalCount: criticalCount,
      onTimeRate: onTimeRate,
      selectedStation: orderedStations.find(function (station) {
        return station.id === state.selectedStationId;
      }) || orderedStations[0],
    };
  }

  function renderMetricCards(simulation) {
    var scenarioLabel = activeScenario().label;
    var metrics = [
      {
        label: state.role === "user" ? "Display mode" : "Active scenario",
        value: scenarioLabel,
        meta:
          state.role === "user" && state.previewScenarioId !== "live"
            ? "Preview only. Live operations continue in the banner."
            : "Live operational context from the MetroTwin control plane.",
      },
      {
        label: "Estimated delay impact",
        value: state.liveState.delay_minutes + " min",
        meta: "Network-level delay estimate under the current live situation.",
      },
      {
        label: state.role === "staff" ? "Evacuation / buildup" : "Critical stations",
        value:
          state.role === "staff"
            ? (state.liveState.evacuation_estimate || 0) + " pax"
            : String(simulation.criticalCount),
        meta:
          state.role === "staff"
            ? "Approximate passengers needing controlled movement or queue management."
            : "Stations currently at critical or closed status.",
      },
      {
        label: "Service reliability",
        value: simulation.onTimeRate + "%",
        meta: "Illustrative on-time performance under this operating condition.",
      },
    ];

    elements.summaryMetrics.innerHTML = metrics
      .map(function (metric) {
        return (
          '<article class="metric-card">' +
          '<span class="metric-card__label">' +
          core.escapeHTML(metric.label) +
          "</span>" +
          '<strong class="metric-card__value">' +
          core.escapeHTML(metric.value) +
          "</strong>" +
          '<small class="metric-card__meta">' +
          core.escapeHTML(metric.meta) +
          "</small>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderModeSummary() {
    var liveLabel = state.liveState.scenario.label;
    var displayLabel = activeScenario().label;
    var previewCopy =
      state.role === "user" && state.previewScenarioId !== "live"
        ? "<strong>Previewing:</strong> " + core.escapeHTML(displayLabel) + "<br><small>Live incident remains " + core.escapeHTML(liveLabel) + ".</small>"
        : "<strong>Live:</strong> " + core.escapeHTML(liveLabel) + "<br><small>Updated " + core.escapeHTML(core.formatRelativeTime(state.liveState.generated_at)) + "</small>";

    elements.modeSummary.innerHTML =
      '<div class="mode-badge">' +
      previewCopy +
      "</div>";
  }

  function renderAlerts() {
    if (!state.liveState.alerts.length) {
      elements.alertBanner.innerHTML = "";
      return;
    }

    elements.alertBanner.innerHTML = state.liveState.alerts
      .slice(0, 3)
      .map(function (alert) {
        return (
          '<article class="alert-card alert-card--' +
          core.severityTone(alert.severity) +
          '">' +
          "<strong>" +
          core.escapeHTML(alert.title) +
          "</strong>" +
          "<p>" +
          core.escapeHTML(alert.message) +
          "</p>" +
          "<small>Issued " +
          core.escapeHTML(core.formatRelativeTime(alert.created_at)) +
          "</small>" +
          "</article>"
        );
      })
      .join("");
  }

  function renderPreviewControls() {
    if (state.role !== "user" || !elements.previewControls) {
      return;
    }

    var controls = [
      { id: "live", label: "Live feed" },
      { id: "normal", label: "Normal" },
      { id: "rush-hour", label: "Rush Hour" },
      { id: "event-surge", label: "Event Surge" },
    ];

    elements.previewControls.innerHTML = controls
      .map(function (item) {
        return (
          '<button type="button" class="scenario-pill ' +
          (state.previewScenarioId === item.id ? "scenario-pill--active" : "") +
          '" data-preview-id="' +
          item.id +
          '">' +
          core.escapeHTML(item.label) +
          "</button>"
        );
      })
      .join("");
  }

  function renderLegend() {
    elements.mapLegend.innerHTML = state.bootstrap.network.lines
      .filter(function (line) {
        return line.id !== "transfer";
      })
      .map(function (line) {
        return (
          '<span class="legend-chip"><span class="legend-chip__dot" style="background:' +
          line.color +
          '"></span>' +
          core.escapeHTML(line.name) +
          "</span>"
        );
      })
      .join("");
  }

  function renderMap(simulation) {
    var stationsById = asLookup(state.bootstrap.network.stations);
    var affectedSegments = new Set(affectedSegmentIds());
    var affectedStations = new Set(affectedStationIds());

    var svg =
      '<svg viewBox="60 120 820 410" class="metro-svg" role="img" aria-label="Metro network map">' +
      state.bootstrap.network.segments
        .map(function (segment) {
          var fromStation = stationsById[segment.from];
          var toStation = stationsById[segment.to];
          var classes = ["metro-segment", "metro-segment--" + segment.line];
          if (segment.kind === "transfer") {
            classes.push("metro-segment--transfer");
          }
          if (affectedSegments.has(segment.id)) {
            classes.push("metro-segment--affected");
          }
          return (
            '<line class="' +
            classes.join(" ") +
            '" x1="' +
            fromStation.x +
            '" y1="' +
            fromStation.y +
            '" x2="' +
            toStation.x +
            '" y2="' +
            toStation.y +
            '"></line>'
          );
        })
        .join("") +
      simulation.stations
        .map(function (station) {
          var classes = [
            "station-node",
            "station-node--" + core.crowdTone(station.crowdLevel),
            "station-node--" + core.statusTone(station.status),
          ];
          if (state.selectedStationId === station.id) {
            classes.push("station-node--selected");
          }
          if (affectedStations.has(station.id)) {
            classes.push("station-node--affected");
          }
          return (
            '<g class="' +
            classes.join(" ") +
            '">' +
            '<circle class="station-hit" cx="' +
            station.x +
            '" cy="' +
            station.y +
            '" r="16" data-station-id="' +
            station.id +
            '"></circle>' +
            '<circle class="station-core" cx="' +
            station.x +
            '" cy="' +
            station.y +
            '" r="8"></circle>' +
            '<text class="station-label" x="' +
            station.x +
            '" y="' +
            (station.y + 26) +
            '">' +
            core.escapeHTML(station.name) +
            "</text>" +
            "</g>"
          );
        })
        .join("") +
      simulation.trains
        .map(function (train) {
          return (
            '<g class="train-marker train-marker--' +
            train.line +
            " train-marker--" +
            train.status +
            '">' +
            '<circle cx="' +
            train.x +
            '" cy="' +
            train.y +
            '" r="6"></circle>' +
            "<title>" +
            train.id +
            " " +
            train.status +
            "</title>" +
            "</g>"
          );
        })
        .join("") +
      "</svg>";

    elements.map.innerHTML = svg;
    elements.map.querySelectorAll("[data-station-id]").forEach(function (node) {
      node.addEventListener("click", function () {
        state.selectedStationId = node.dataset.stationId;
        renderFrame();
      });
    });
  }

  function renderStationInspector(simulation) {
    var station = simulation.stationsById[state.selectedStationId] || simulation.selectedStation;
    if (!station) {
      elements.stationInspector.innerHTML = '<div class="empty-state">Select a station on the map.</div>';
      return;
    }

    elements.stationInspector.innerHTML =
      '<div class="inspector-card inspector-card--' +
      core.crowdTone(station.crowdLevel) +
      '">' +
      "<h3>" +
      core.escapeHTML(station.name) +
      "</h3>" +
      '<div class="inspector-stat"><span>Crowd</span><strong>' +
      core.escapeHTML(station.crowdLevel) +
      "</strong></div>" +
      '<div class="inspector-stat"><span>Passengers</span><strong>' +
      station.projectedPassengers +
      " / " +
      station.projectedCapacity +
      "</strong></div>" +
      '<div class="inspector-stat"><span>Service</span><strong>' +
      core.escapeHTML(station.status) +
      "</strong></div>" +
      '<div class="inspector-stat"><span>Next train</span><strong>' +
      core.escapeHTML(station.nextTrain) +
      "</strong></div>" +
      '<div class="progress-bar"><span style="width:' +
      Math.min(100, Math.round(station.utilization * 100)) +
      '%"></span></div>' +
      "</div>";
  }

  function renderLiveSituation(simulation) {
    var incident = state.liveState.incident;
    var affectedStations = state.liveState.affected_stations
      .map(function (station) {
        return station.name;
      })
      .join(", ");
    var affectedSegments = state.liveState.affected_segments
      .map(function (segment) {
        return segment.label;
      })
      .join(", ");

    var rows = [
      ["Live scenario", state.liveState.scenario.label],
      ["Display scenario", activeScenario().label],
      ["Estimated delay", state.liveState.delay_minutes + " min"],
      ["Network passengers", simulation.totalPassengers.toLocaleString()],
    ];

    if (incident) {
      rows.push(["Affected stations", affectedStations || "Operational review"]);
      rows.push(["Affected segments", affectedSegments || "None selected"]);
    }

    elements.liveSituation.innerHTML = rows
      .map(function (row) {
        return (
          '<div class="info-row"><span>' +
          core.escapeHTML(row[0]) +
          "</span><strong>" +
          core.escapeHTML(row[1]) +
          "</strong></div>"
        );
      })
      .join("");
  }

  function renderLineChart(container, values, label) {
    if (!container) {
      return;
    }
    var width = 360;
    var height = 180;
    var padding = 18;
    var max = Math.max.apply(null, values);
    var min = Math.min.apply(null, values);
    var range = Math.max(1, max - min);

    var points = values
      .map(function (value, index) {
        var x = padding + (index / (values.length - 1)) * (width - padding * 2);
        var y = height - padding - ((value - min) / range) * (height - padding * 2);
        return x + "," + y;
      })
      .join(" ");

    container.innerHTML =
      '<svg viewBox="0 0 ' +
      width +
      " " +
      height +
      '" class="chart-svg">' +
      '<polyline class="chart-line" points="' +
      points +
      '"></polyline>' +
      values
        .map(function (value, index) {
          var x = padding + (index / (values.length - 1)) * (width - padding * 2);
          var y = height - padding - ((value - min) / range) * (height - padding * 2);
          return '<circle class="chart-point" cx="' + x + '" cy="' + y + '" r="4"></circle>';
        })
        .join("") +
      "</svg>" +
      '<div class="chart-footnote">' +
      core.escapeHTML(label) +
      "</div>";
  }

  function renderCongestionChart(simulation) {
    if (!elements.congestionChart) {
      return;
    }

    var items = simulation.stations.slice(0, 6);
    elements.congestionChart.innerHTML = items
      .map(function (station) {
        return (
          '<div class="bar-row">' +
          "<span>" +
          core.escapeHTML(station.name) +
          "</span>" +
          '<div class="bar-track"><div class="bar-fill bar-fill--' +
          core.crowdTone(station.crowdLevel) +
          '" style="width:' +
          Math.min(100, Math.round(station.utilization * 100)) +
          '%"></div></div>' +
          "<strong>" +
          Math.round(station.utilization * 100) +
          "%</strong>" +
          "</div>"
        );
      })
      .join("");
  }

  function renderDelayChart() {
    var effectiveId = activeScenario().id;
    elements.delayChart.innerHTML = state.liveState.delay_matrix
      .map(function (item) {
        return (
          '<div class="bar-row">' +
          "<span>" +
          core.escapeHTML(item.label) +
          "</span>" +
          '<div class="bar-track"><div class="bar-fill bar-fill--' +
          (item.id === effectiveId ? "critical" : "neutral") +
          '" style="width:' +
          Math.min(100, item.delay_minutes * 2.8) +
          '%"></div></div>' +
          "<strong>" +
          item.delay_minutes +
          "m</strong></div>"
        );
      })
      .join("");
  }

  function renderPassengerChart(simulation) {
    var values = [];
    for (var index = 0; index < 10; index += 1) {
      var wave = 0.92 + Math.sin((state.tick + index) / 2.7) * 0.08 + index * 0.01;
      values.push(Math.round(simulation.totalPassengers * wave));
    }
    renderLineChart(elements.passengerChart, values, "Projected passenger volume across the next 20 minutes");
  }

  function renderStationCards(simulation) {
    elements.stationCards.innerHTML = simulation.stations
      .map(function (station) {
        return (
          '<button type="button" class="station-card station-card--' +
          core.crowdTone(station.crowdLevel) +
          '" data-station-focus="' +
          station.id +
          '">' +
          '<div class="station-card__head"><strong>' +
          core.escapeHTML(station.name) +
          '</strong><span class="pill pill--' +
          core.statusTone(station.status) +
          '">' +
          core.escapeHTML(station.status) +
          "</span></div>" +
          '<div class="station-card__meta"><span>Crowd</span><strong>' +
          core.escapeHTML(station.crowdLevel) +
          "</strong></div>" +
          '<div class="station-card__meta"><span>Next train</span><strong>' +
          core.escapeHTML(station.nextTrain) +
          "</strong></div>" +
          '<div class="station-card__meta"><span>Line</span><strong>' +
          core.escapeHTML(station.line.toUpperCase()) +
          "</strong></div>" +
          "</button>"
        );
      })
      .join("");

    elements.stationCards.querySelectorAll("[data-station-focus]").forEach(function (button) {
      button.addEventListener("click", function () {
        state.selectedStationId = button.dataset.stationFocus;
        renderFrame();
      });
    });
  }

  function renderRecommendedActions() {
    if (!elements.recommendedActions) {
      return;
    }
    elements.recommendedActions.innerHTML = state.liveState.recommended_actions
      .map(function (action) {
        return "<p>" + core.escapeHTML(action) + "</p>";
      })
      .join("");
  }

  function renderBottlenecks() {
    if (!elements.bottleneckList) {
      return;
    }
    elements.bottleneckList.innerHTML = state.liveState.bottlenecks
      .map(function (station) {
        return (
          '<div class="bottleneck-row">' +
          "<strong>" +
          core.escapeHTML(station.name) +
          '</strong><span class="pill pill--' +
          core.crowdTone(station.crowd_level) +
          '">' +
          core.escapeHTML(station.crowd_level) +
          "</span><small>" +
          Math.round(station.utilization * 100) +
          "% utilization</small></div>"
        );
      })
      .join("");
  }

  function renderFrame() {
    var simulation = buildSimulation();
    state.selectedStationId = simulation.selectedStation.id;
    renderMetricCards(simulation);
    renderModeSummary();
    renderAlerts();
    renderLegend();
    renderPreviewControls();
    renderMap(simulation);
    renderStationInspector(simulation);
    renderLiveSituation(simulation);
    renderPassengerChart(simulation);
    renderCongestionChart(simulation);
    renderDelayChart();
    renderStationCards(simulation);
    renderRecommendedActions();
    renderBottlenecks();
  }

  function populateScenarioControls() {
    if (state.role !== "staff") {
      return;
    }

    elements.scenarioSelect.innerHTML = state.bootstrap.scenarios
      .map(function (scenario) {
        return (
          '<option value="' +
          scenario.id +
          '">' +
          core.escapeHTML(scenario.label) +
          "</option>"
        );
      })
      .join("");

    elements.stationCheckboxes.innerHTML = state.bootstrap.network.stations
      .map(function (station) {
        return (
          '<label class="check-chip"><input type="checkbox" name="affected_station_ids" value="' +
          station.id +
          '"><span>' +
          core.escapeHTML(station.name) +
          "</span></label>"
        );
      })
      .join("");

    elements.segmentCheckboxes.innerHTML = state.bootstrap.network.segments
      .filter(function (segment) {
        return segment.kind === "rail";
      })
      .map(function (segment) {
        var fromName = state.bootstrap.network.stations.find(function (station) {
          return station.id === segment.from;
        }).name;
        var toName = state.bootstrap.network.stations.find(function (station) {
          return station.id === segment.to;
        }).name;
        return (
          '<label class="check-chip"><input type="checkbox" name="affected_segment_ids" value="' +
          segment.id +
          '"><span>' +
          core.escapeHTML(fromName + " - " + toName) +
          "</span></label>"
        );
      })
      .join("");
  }

  function collectCheckedValues(name) {
    return Array.prototype.slice
      .call(document.querySelectorAll('input[name="' + name + '"]:checked'))
      .map(function (input) {
        return input.value;
      });
  }

  function bindStaffControls() {
    populateScenarioControls();

    elements.scenarioForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      var formData = new FormData(elements.scenarioForm);
      var payload = {
        scenario_id: String(formData.get("scenario_id") || "normal"),
        affected_station_ids: collectCheckedValues("affected_station_ids"),
        affected_segment_ids: collectCheckedValues("affected_segment_ids"),
        notes: String(formData.get("notes") || "").trim(),
      };

      elements.scenarioMessage.textContent = "Applying scenario...";
      elements.scenarioMessage.className = "form-message";

      try {
        state.liveState = await core.requestJSON("/api/staff/scenario", {
          method: "POST",
          body: payload,
        });
        elements.scenarioMessage.textContent = "Scenario updated.";
        elements.scenarioMessage.className = "form-message form-message--success";
        renderFrame();
        core.showToast("Scenario applied.", "warning");
      } catch (error) {
        elements.scenarioMessage.textContent = error.message;
        elements.scenarioMessage.className = "form-message form-message--error";
        core.showToast(error.message, "critical");
      }
    });

    elements.resetScenarioButton.addEventListener("click", async function () {
      try {
        state.liveState = await core.requestJSON("/api/staff/resolve", {
          method: "POST",
        });
        elements.scenarioForm.reset();
        elements.scenarioMessage.textContent = "Network returned to normal operation.";
        elements.scenarioMessage.className = "form-message form-message--success";
        renderFrame();
        core.showToast("Network set to normal.", "info");
      } catch (error) {
        core.showToast(error.message, "critical");
      }
    });

    elements.alertForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      var formData = new FormData(elements.alertForm);
      var payload = {
        title: String(formData.get("title") || "").trim(),
        message: String(formData.get("message") || "").trim(),
        severity: String(formData.get("severity") || "warning"),
      };

      elements.alertMessage.textContent = "Publishing...";
      elements.alertMessage.className = "form-message";

      try {
        var response = await core.requestJSON("/api/alerts", {
          method: "POST",
          body: payload,
        });
        state.liveState = response.live_state;
        elements.alertForm.reset();
        elements.alertMessage.textContent = "Public alert sent.";
        elements.alertMessage.className = "form-message form-message--success";
        renderFrame();
        core.showToast("Public alert sent.", "info");
      } catch (error) {
        elements.alertMessage.textContent = error.message;
        elements.alertMessage.className = "form-message form-message--error";
        core.showToast(error.message, "critical");
      }
    });
  }

  async function syncLiveState() {
    try {
      state.liveState = await core.requestJSON("/api/live-state");
      renderFrame();
    } catch (error) {
      core.showToast(error.message, "critical");
    }
  }

  function startLoops() {
    state.timers.push(
      window.setInterval(function () {
        state.tick += 1;
        renderFrame();
      }, 1000)
    );

    state.timers.push(
      window.setInterval(function () {
        syncLiveState();
      }, 15000)
    );
  }

  async function init() {
    state.bootstrap = await core.requestJSON("/api/bootstrap");
    state.liveState = state.bootstrap.live_state;

    state.bootstrap.scenarios
      .concat([state.liveState.scenario])
      .forEach(function (scenario) {
        state.scenarioLookup[scenario.id] = scenario;
      });

    if (state.role === "staff") {
      bindStaffControls();
    } else if (elements.previewControls) {
      elements.previewControls.addEventListener("click", function (event) {
        var button = event.target.closest("[data-preview-id]");
        if (!button) {
          return;
        }
        state.previewScenarioId = button.dataset.previewId;
        renderFrame();
      });
    }

    renderFrame();
    startLoops();
  }

  init().catch(function (error) {
    core.showToast(error.message, "critical");
    if (elements.map) {
      elements.map.innerHTML = '<div class="empty-state">Unable to load dashboard data.</div>';
    }
  });
});
