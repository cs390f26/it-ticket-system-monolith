// Shared helpers for the help desk pages. Every page talks to the JSON API
// with relative URLs, so the pages work wherever the Flask app is served.

const STATUS_CLASSES = {
  Open: "status-open",
  "In progress": "status-progress",
  Resolved: "status-resolved",
};

function formatDate(iso, withTime = true) {
  const options = { month: "short", day: "numeric", year: "numeric" };
  if (withTime) {
    options.hour = "numeric";
    options.minute = "2-digit";
  }
  return new Date(iso).toLocaleString("en-US", options);
}

function badge(text, className) {
  const span = document.createElement("span");
  span.className = "badge " + className;
  span.textContent = text;
  return span;
}

function priorityBadge(priority) {
  return badge(priority, "priority-" + priority.toLowerCase());
}

function statusBadge(status) {
  return badge(status, STATUS_CLASSES[status] || "");
}

// Returns { ok, status, data }. A network failure comes back as status 0
// with an error message in the same shape the API uses.
async function api(url, options = {}) {
  const init = { ...options, headers: { ...(options.headers || {}) } };
  if (init.body !== undefined && typeof init.body !== "string") {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(init.body);
  }
  try {
    const response = await fetch(url, init);
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
  } catch {
    return {
      ok: false,
      status: 0,
      data: { error: { message: "Could not reach the server. Try again." } },
    };
  }
}

function errorMessage(result, fallback) {
  return (result.data && result.data.error && result.data.error.message) || fallback;
}

function showBanner(element, message, kind) {
  element.className = "banner banner-" + kind;
  element.textContent = message;
  element.hidden = false;
}

function hideBanner(element) {
  element.hidden = true;
  element.textContent = "";
}

function setBusy(button, busy, busyLabel) {
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}
