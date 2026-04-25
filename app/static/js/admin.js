document.addEventListener("DOMContentLoaded", function () {
  if (document.body.dataset.page !== "admin" || !window.NexusCore) {
    return;
  }

  var state = {
    staffAccounts: [],
  };

  var metricsEl = document.getElementById("admin-metrics");
  var listEl = document.getElementById("staff-list");
  var form = document.getElementById("staff-create-form");
  var messageEl = document.getElementById("staff-create-message");

  function renderMetrics() {
    var total = state.staffAccounts.length;
    var active = state.staffAccounts.filter(function (account) {
      return account.is_active;
    }).length;
    var admins = state.staffAccounts.filter(function (account) {
      return account.role === "admin";
    }).length;

    metricsEl.innerHTML = [
      metricCard("Staff accounts", total, "Seeded and admin-created accounts"),
      metricCard("Active", active, "Users currently able to access the staff portal"),
      metricCard("Admins", admins, "Privileged accounts with staff management access"),
    ].join("");
  }

  function metricCard(label, value, detail) {
    return (
      '<article class="metric-card">' +
      '<span class="metric-card__label">' +
      label +
      "</span>" +
      '<strong class="metric-card__value">' +
      value +
      "</strong>" +
      '<small class="metric-card__meta">' +
      detail +
      "</small>" +
      "</article>"
    );
  }

  function renderList() {
    if (!state.staffAccounts.length) {
      listEl.innerHTML = '<div class="empty-state">No staff accounts found.</div>';
      return;
    }

    listEl.innerHTML =
      '<table class="staff-table">' +
      "<thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>" +
      "<tbody>" +
      state.staffAccounts
        .map(function (account) {
          return (
            "<tr>" +
            "<td><strong>" +
            window.NexusCore.escapeHTML(account.name) +
            "</strong></td>" +
            "<td>" +
            window.NexusCore.escapeHTML(account.email) +
            "</td>" +
            "<td><span class=\"pill pill--neutral\">" +
            window.NexusCore.escapeHTML(account.role) +
            "</span></td>" +
            "<td><span class=\"pill pill--" +
            (account.is_active ? "ok" : "warning") +
            "\">" +
            (account.is_active ? "Active" : "Inactive") +
            "</span></td>" +
            '<td class="action-cell">' +
            '<button class="button button--ghost button--small" data-action="toggle" data-id="' +
            account.id +
            '">' +
            (account.is_active ? "Deactivate" : "Activate") +
            "</button>" +
            '<button class="button button--ghost button--small" data-action="promote" data-id="' +
            account.id +
            '">' +
            (account.role === "admin" ? "Set Staff" : "Set Admin") +
            "</button>" +
            '<button class="button button--danger button--small" data-action="delete" data-id="' +
            account.id +
            '">Delete</button>' +
            "</td>" +
            "</tr>"
          );
        })
        .join("") +
      "</tbody></table>";
  }

  async function loadStaffAccounts() {
    var payload = await window.NexusCore.requestJSON("/api/admin/staff");
    state.staffAccounts = payload.staff_accounts;
    renderMetrics();
    renderList();
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    var formData = new FormData(form);
    var payload = {
      name: String(formData.get("name") || "").trim(),
      email: String(formData.get("email") || "").trim(),
      password: String(formData.get("password") || ""),
      role: String(formData.get("role") || "staff"),
    };

    messageEl.textContent = "Creating account...";
    messageEl.className = "form-message";

    try {
      await window.NexusCore.requestJSON("/api/admin/staff", {
        method: "POST",
        body: payload,
      });
      form.reset();
      messageEl.textContent = "Staff account created.";
      messageEl.className = "form-message form-message--success";
      window.NexusCore.showToast("Staff account created.", "info");
      await loadStaffAccounts();
    } catch (error) {
      messageEl.textContent = error.message;
      messageEl.className = "form-message form-message--error";
      window.NexusCore.showToast(error.message, "critical");
    }
  });

  listEl.addEventListener("click", async function (event) {
    var button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    var accountId = button.dataset.id;
    var action = button.dataset.action;
    var account = state.staffAccounts.find(function (item) {
      return item.id === accountId;
    });
    if (!account) {
      return;
    }

    try {
      if (action === "toggle") {
        await window.NexusCore.requestJSON("/api/admin/staff/" + accountId, {
          method: "PATCH",
          body: { is_active: !account.is_active },
        });
        window.NexusCore.showToast("Account status updated.", "info");
      } else if (action === "promote") {
        await window.NexusCore.requestJSON("/api/admin/staff/" + accountId, {
          method: "PATCH",
          body: { role: account.role === "admin" ? "staff" : "admin" },
        });
        window.NexusCore.showToast("Account role updated.", "info");
      } else if (action === "delete") {
        if (!window.confirm("Delete this staff account?")) {
          return;
        }
        await window.NexusCore.requestJSON("/api/admin/staff/" + accountId, {
          method: "DELETE",
        });
        window.NexusCore.showToast("Staff account deleted.", "warning");
      }
      await loadStaffAccounts();
    } catch (error) {
      window.NexusCore.showToast(error.message, "critical");
    }
  });

  loadStaffAccounts().catch(function (error) {
    window.NexusCore.showToast(error.message, "critical");
  });
});

