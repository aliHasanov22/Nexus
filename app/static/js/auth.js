document.addEventListener("DOMContentLoaded", function () {
  var form = document.querySelector(".auth-form");
  if (!form || !window.NexusCore) {
    return;
  }

  var messageEl = document.getElementById("auth-message");

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    var mode = form.dataset.mode || "login";
    var portal = form.dataset.portal || "public";
    var submitButton = form.querySelector('button[type="submit"]');
    var formData = new FormData(form);
    var payload = {
      email: String(formData.get("email") || "").trim(),
      password: String(formData.get("password") || ""),
    };

    if (mode === "register") {
      payload.name = String(formData.get("name") || "").trim();
    } else {
      payload.portal = portal;
    }

    submitButton.disabled = true;
    messageEl.textContent = "Connecting...";
    messageEl.className = "form-message";

    try {
      var response = await window.NexusCore.requestJSON(
        mode === "register" ? "/api/auth/register" : "/api/auth/login",
        {
          method: "POST",
          body: payload,
        }
      );
      window.location.href = response.redirect_to;
    } catch (error) {
      messageEl.textContent = error.message;
      messageEl.className = "form-message form-message--error";
      window.NexusCore.showToast(error.message, "critical");
    } finally {
      submitButton.disabled = false;
    }
  });
});

