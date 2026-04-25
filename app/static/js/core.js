(function () {
  function parseResponse(response) {
    return response
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        if (!response.ok) {
          var message = data.detail || data.message || "Request failed.";
          throw new Error(message);
        }
        return data;
      });
  }

  async function requestJSON(url, options) {
    var requestOptions = Object.assign({ method: "GET", headers: {} }, options || {});
    requestOptions.headers = Object.assign({}, requestOptions.headers);

    if (requestOptions.body && typeof requestOptions.body !== "string") {
      requestOptions.headers["Content-Type"] = "application/json";
      requestOptions.body = JSON.stringify(requestOptions.body);
    }

    var response = await fetch(url, requestOptions);
    return parseResponse(response);
  }

  function showToast(message, tone) {
    var toast = document.getElementById("toast");
    if (!toast) {
      return;
    }

    toast.textContent = message;
    toast.className = "toast toast--visible toast--" + (tone || "info");
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(function () {
      toast.className = "toast";
    }, 2800);
  }

  function formatRelativeTime(value) {
    if (!value) {
      return "now";
    }
    var then = new Date(value);
    var diffSeconds = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
    if (diffSeconds < 60) {
      return diffSeconds + "s ago";
    }
    if (diffSeconds < 3600) {
      return Math.round(diffSeconds / 60) + "m ago";
    }
    return Math.round(diffSeconds / 3600) + "h ago";
  }

  function crowdTone(level) {
    var map = {
      Low: "low",
      Medium: "medium",
      High: "high",
      Critical: "critical",
    };
    return map[level] || "low";
  }

  function statusTone(status) {
    var map = {
      normal: "stable",
      crowded: "warning",
      emergency: "critical",
      closed: "critical",
    };
    return map[status] || "stable";
  }

  function severityTone(severity) {
    return severity || "info";
  }

  function escapeHTML(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function byId(id) {
    return document.getElementById(id);
  }

  window.NexusCore = {
    requestJSON: requestJSON,
    showToast: showToast,
    formatRelativeTime: formatRelativeTime,
    crowdTone: crowdTone,
    statusTone: statusTone,
    severityTone: severityTone,
    escapeHTML: escapeHTML,
    byId: byId,
  };
})();
