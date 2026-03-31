import "./styles.css";

const app = document.querySelector("#app");
const API_BASE = "/api/v1";

app.innerHTML = `
  <div class="container">
    <header>
      <h1>IoT Dashboard</h1>
      <p>Create groups and devices from the architecture spec.</p>
    </header>

    <section class="card">
      <h2>Create Group</h2>
      <form id="group-form">
        <label>
          Group Name
          <input type="text" name="name" placeholder="Farm Sensors" required />
        </label>
        <label>
          Group ID (optional)
          <input type="text" name="group_id" placeholder="grp_farm_01" />
        </label>
        <button type="submit">Create Group</button>
      </form>
    </section>

    <section class="card">
      <h2>Groups</h2>
      <div id="groups" class="list"></div>
    </section>

    <section class="card" id="devices-section">
      <h2>Devices</h2>
      <div id="selected-group" class="muted">Select a group to manage devices.</div>
      <div id="credentials" class="hidden"></div>
      <div id="device-detail" class="hidden"></div>
      <form id="device-form" class="hidden">
        <label>
          Device Name
          <input type="text" name="name" placeholder="Weather Station" />
        </label>
        <button type="submit">Create Device</button>
      </form>
      <div id="devices" class="list"></div>
    </section>

    <section class="card" id="monitor-section">
      <h2>Telemetry Monitor (MongoDB)</h2>
      <div id="selected-device" class="muted">Select a device to view telemetry.</div>
      <div id="telemetry" class="list"></div>
    </section>
  </div>
`;

const groupForm = document.querySelector("#group-form");
const deviceForm = document.querySelector("#device-form");
const groupsEl = document.querySelector("#groups");
const devicesEl = document.querySelector("#devices");
const selectedGroupEl = document.querySelector("#selected-group");
const credentialsEl = document.querySelector("#credentials");
const deviceDetailEl = document.querySelector("#device-detail");
const telemetryEl = document.querySelector("#telemetry");
const selectedDeviceEl = document.querySelector("#selected-device");

let selectedGroupId = null;
let selectedDeviceId = null;
let telemetryTimer = null;

async function fetchJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Request failed");
  }
  return res.json();
}

async function loadGroups() {
  groupsEl.innerHTML = "<div class=\"muted\">Loading groups...</div>";
  try {
    const groups = await fetchJson(`${API_BASE}/groups`);
    if (!groups.length) {
      groupsEl.innerHTML = "<div class=\"muted\">No groups yet.</div>";
      return;
    }
    groupsEl.innerHTML = groups
      .map(
        (g) => `
        <button class="list-item" data-group-id="${g.group_id}">
          <div>
            <strong>${g.name}</strong>
            <div class="muted">${g.group_id}</div>
          </div>
          <span class="pill">${new Date(g.created_at).toLocaleString()}</span>
        </button>
      `
      )
      .join("");
  } catch (err) {
    groupsEl.innerHTML = `<div class=\"error\">${err.message}</div>`;
  }
}

async function loadDevices(groupId) {
  devicesEl.innerHTML = "<div class=\"muted\">Loading devices...</div>";
  try {
    const devices = await fetchJson(`${API_BASE}/groups/${groupId}/devices`);
    if (!devices.length) {
      devicesEl.innerHTML = "<div class=\"muted\">No devices yet.</div>";
      return;
    }
    devicesEl.innerHTML = devices
      .map(
        (d) => `
        <button class="list-item" data-device-id="${d.device_id}">
          <div>
            <strong>${d.device_id}</strong>
            <div class="muted">${d.name || "Unnamed device"}</div>
          </div>
          <span class="pill">${new Date(d.created_at).toLocaleString()}</span>
        </button>
      `
      )
      .join("");
  } catch (err) {
    devicesEl.innerHTML = `<div class=\"error\">${err.message}</div>`;
  }
}

async function loadTelemetry(deviceId) {
  telemetryEl.innerHTML = "<div class=\"muted\">Loading telemetry...</div>";
  try {
    const res = await fetchJson(`/broker/api/v1/devices/${deviceId}/telemetry?limit=50`);
    if (!res.data || !res.data.length) {
      telemetryEl.innerHTML = "<div class=\"muted\">No telemetry yet.</div>";
      return;
    }
    telemetryEl.innerHTML = res.data
      .map(
        (item) => `
        <div class="message-item">
          <div>
            <div class="message-topic">${item.topic || "telemetry"}</div>
            <div class="muted">${new Date(item.timestamp).toLocaleString()}</div>
          </div>
          <pre>${JSON.stringify(item, null, 2)}</pre>
        </div>
      `
      )
      .join("");
  } catch (err) {
    telemetryEl.innerHTML = `<div class=\"error\">${err.message}</div>`;
  }
}

function selectGroup(groupId) {
  selectedGroupId = groupId;
  selectedGroupEl.textContent = `Managing devices for ${groupId}`;
  deviceForm.classList.remove("hidden");
  credentialsEl.classList.add("hidden");
  deviceDetailEl.classList.add("hidden");
  selectedDeviceId = null;
  selectedDeviceEl.textContent = "Select a device to view telemetry.";
  telemetryEl.innerHTML = "";
  if (telemetryTimer) {
    clearInterval(telemetryTimer);
    telemetryTimer = null;
  }
  loadDevices(groupId);
}

groupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(groupForm);
  const payload = Object.fromEntries(formData.entries());
  if (!payload.group_id) delete payload.group_id;
  try {
    await fetchJson(`${API_BASE}/groups`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    groupForm.reset();
    await loadGroups();
  } catch (err) {
    alert(err.message);
  }
});

deviceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedGroupId) return;
  const formData = new FormData(deviceForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    const created = await fetchJson(`${API_BASE}/groups/${selectedGroupId}/devices`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    deviceForm.reset();
    credentialsEl.classList.remove("hidden");
    credentialsEl.innerHTML = `
      <div class="credential-card">
        <strong>Device credentials created</strong>
        <div class="muted">Save these values now. They are shown once.</div>
        <div class="credential-row"><span>Device ID</span><code>${created.device_id}</code></div>
        <div class="credential-row"><span>Token</span><code>${created.credentials.token}</code></div>
        <div class="credential-row"><span>Secret</span><code>${created.credentials.secret}</code></div>
      </div>
    `;
    await loadDevices(selectedGroupId);
  } catch (err) {
    alert(err.message);
  }
});

groupsEl.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-group-id]");
  if (!button) return;
  selectGroup(button.dataset.groupId);
});

devicesEl.addEventListener("click", (event) => {
  const deviceButton = event.target.closest("button[data-device-id]");
  if (!deviceButton) return;
  selectedDeviceId = deviceButton.dataset.deviceId;
  selectedDeviceEl.textContent = `Monitoring ${selectedDeviceId}`;
  loadDeviceDetail(selectedDeviceId);
  loadTelemetry(selectedDeviceId);
  if (telemetryTimer) clearInterval(telemetryTimer);
  telemetryTimer = setInterval(() => loadTelemetry(selectedDeviceId), 5000);
});

async function loadDeviceDetail(deviceId) {
  deviceDetailEl.classList.remove("hidden");
  deviceDetailEl.innerHTML = "<div class=\"muted\">Loading device details...</div>";
  try {
    const detail = await fetchJson(`${API_BASE}/groups/${selectedGroupId}/devices/${deviceId}`);
    deviceDetailEl.innerHTML = `
      <div class="credential-card">
        <strong>Device details</strong>
        <form id="device-edit-form">
          <label>
            Device Name
            <input type="text" name="name" value="${detail.name}" />
          </label>
          <button type="submit">Save</button>
        </form>
        <div class="muted">Credentials (hashed)</div>
        <div class="credential-row"><span>Token hash</span><code>${detail.credentials.token_hash}</code></div>
        <div class="credential-row"><span>Secret hash</span><code>${detail.credentials.secret_hash}</code></div>
      </div>
    `;
    const editForm = deviceDetailEl.querySelector("#device-edit-form");
    editForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(editForm);
      const payload = Object.fromEntries(formData.entries());
      try {
        await fetchJson(`${API_BASE}/groups/${selectedGroupId}/devices/${deviceId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        await loadDevices(selectedGroupId);
        await loadDeviceDetail(deviceId);
      } catch (err) {
        alert(err.message);
      }
    });
  } catch (err) {
    deviceDetailEl.innerHTML = `<div class=\"error\">${err.message}</div>`;
  }
}

loadGroups();
