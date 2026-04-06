from __future__ import annotations


def render_operator_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DION ABA1 Operator UI</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --panel-border: #d7cfc0;
      --text: #1f1a14;
      --muted: #6f6558;
      --accent: #0e7490;
      --danger: #b91c1c;
      --ok: #166534;
      --shadow: 0 10px 30px rgba(31, 26, 20, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(14, 116, 144, 0.10), transparent 24%),
        linear-gradient(180deg, #f8f5ef 0%, var(--bg) 100%);
    }

    main {
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px;
    }

    h1, h2, h3 {
      margin: 0 0 12px;
      line-height: 1.1;
    }

    p {
      margin: 0;
      color: var(--muted);
    }

    .hero {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 20px;
      padding: 20px 22px;
      background: linear-gradient(135deg, rgba(14, 116, 144, 0.10), rgba(255, 253, 248, 0.95));
      border: 1px solid var(--panel-border);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }

    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }

    .card {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      padding: 16px;
    }

    .row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }

    .row.single {
      grid-template-columns: minmax(0, 1fr);
    }

    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 6px;
    }

    input, select, button, textarea {
      width: 100%;
      border-radius: 10px;
      border: 1px solid #cfc5b6;
      padding: 10px 12px;
      font: inherit;
      color: var(--text);
      background: #fff;
    }

    textarea {
      min-height: 92px;
      resize: vertical;
    }

    button {
      cursor: pointer;
      background: var(--accent);
      color: #fff;
      border: 0;
      font-weight: 700;
    }

    button.secondary {
      background: #e6dfd2;
      color: var(--text);
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }

    .actions button {
      width: auto;
      min-width: 140px;
    }

    .status-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .status-box {
      border-radius: 14px;
      border: 1px solid var(--panel-border);
      background: rgba(255, 255, 255, 0.78);
      padding: 14px;
    }

    .status-box strong {
      display: block;
      margin-bottom: 6px;
    }

    .ok { color: var(--ok); }
    .error { color: var(--danger); }

    pre {
      margin: 12px 0 0;
      padding: 12px;
      min-height: 140px;
      overflow: auto;
      border-radius: 12px;
      background: #191614;
      color: #f7f2eb;
      font-size: 12px;
      line-height: 1.45;
    }

    .hint {
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
    }

    @media (max-width: 760px) {
      main { padding: 16px; }
      .hero { padding: 16px; }
      .row { grid-template-columns: 1fr; }
      .actions button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <h1>DION ABA1 Operator UI</h1>
        <p>Minimal same-origin UI for exercising the verified backend flow without Swagger.</p>
      </div>
      <p>Entrypoint: <code>/operator</code></p>
    </section>

    <section class="status-strip">
      <div class="status-box">
        <strong>Health</strong>
        <div id="health-status">Loading...</div>
      </div>
      <div class="status-box">
        <strong>Readiness</strong>
        <div id="readiness-status">Loading...</div>
      </div>
    </section>

    <section class="grid">
      <article class="card">
        <h2>System Status</h2>
        <p>Quick backend liveness and readiness checks.</p>
        <div class="actions">
          <button type="button" id="refresh-status">Refresh Status</button>
        </div>
        <pre id="status-output">Waiting for status...</pre>
      </article>

      <article class="card">
        <h2>Resolve User Identity</h2>
        <p>Resolve by seeded demo user ID or user code.</p>
        <div class="row">
          <div>
            <label for="auth-user-id">user_id</label>
            <input id="auth-user-id" name="auth-user-id" type="number" value="3">
          </div>
          <div>
            <label for="auth-user-code">user_code</label>
            <input id="auth-user-code" name="auth-user-code" type="text" value="user-1">
          </div>
        </div>
        <div class="actions">
          <button type="button" id="auth-by-id">Resolve by user_id</button>
          <button type="button" class="secondary" id="auth-by-code">Resolve by user_code</button>
        </div>
        <pre id="auth-output">Ready.</pre>
      </article>

      <article class="card">
        <h2>Inventory Lookup</h2>
        <p>Inspect the seeded slot and item pair.</p>
        <div class="row">
          <div>
            <label for="inventory-slot-id">slot_id</label>
            <input id="inventory-slot-id" name="inventory-slot-id" type="number" value="1">
          </div>
          <div>
            <label for="inventory-item-id">item_id</label>
            <input id="inventory-item-id" name="inventory-item-id" type="number" value="1">
          </div>
        </div>
        <div class="actions">
          <button type="button" id="inventory-run">Lookup Inventory</button>
        </div>
        <pre id="inventory-output">Ready.</pre>
      </article>

      <article class="card">
        <h2>Dispense</h2>
        <p>Verified happy-path dispense call. Leave session empty for null.</p>
        <div class="row">
          <div>
            <label for="dispense-user-id">user_id</label>
            <input id="dispense-user-id" name="dispense-user-id" type="number" value="3">
          </div>
          <div>
            <label for="dispense-item-id">item_id</label>
            <input id="dispense-item-id" name="dispense-item-id" type="number" value="1">
          </div>
        </div>
        <div class="row">
          <div>
            <label for="dispense-slot-id">slot_id</label>
            <input id="dispense-slot-id" name="dispense-slot-id" type="number" value="1">
          </div>
          <div>
            <label for="dispense-quantity">quantity</label>
            <input id="dispense-quantity" name="dispense-quantity" type="number" value="1" min="1">
          </div>
        </div>
        <div class="row single">
          <div>
            <label for="dispense-session-id">session_id</label>
            <input id="dispense-session-id" name="dispense-session-id" type="number" placeholder="Empty sends null">
          </div>
        </div>
        <div class="actions">
          <button type="button" id="dispense-run">Execute Dispense</button>
        </div>
        <pre id="dispense-output">Ready.</pre>
      </article>

      <article class="card">
        <h2>Return</h2>
        <p>Verified return call. Keep session empty for null. Clear slot if you want backend auto-resolution.</p>
        <div class="row">
          <div>
            <label for="return-user-id">user_id</label>
            <input id="return-user-id" name="return-user-id" type="number" value="3">
          </div>
          <div>
            <label for="return-item-id">item_id</label>
            <input id="return-item-id" name="return-item-id" type="number" value="1">
          </div>
        </div>
        <div class="row">
          <div>
            <label for="return-slot-id">slot_id</label>
            <input id="return-slot-id" name="return-slot-id" type="number" value="1" placeholder="Empty sends null">
          </div>
          <div>
            <label for="return-quantity">quantity</label>
            <input id="return-quantity" name="return-quantity" type="number" value="1" min="1">
          </div>
        </div>
        <div class="row single">
          <div>
            <label for="return-session-id">session_id</label>
            <input id="return-session-id" name="return-session-id" type="number" placeholder="Empty sends null">
          </div>
        </div>
        <div class="actions">
          <button type="button" id="return-run">Execute Return</button>
        </div>
        <pre id="return-output">Ready.</pre>
      </article>

      <article class="card">
        <h2>Refill</h2>
        <p>Verified refill call for the seeded operator and slot.</p>
        <div class="row">
          <div>
            <label for="refill-operator-user-id">operator_user_id</label>
            <input id="refill-operator-user-id" name="refill-operator-user-id" type="number" value="2">
          </div>
          <div>
            <label for="refill-item-id">item_id</label>
            <input id="refill-item-id" name="refill-item-id" type="number" value="1">
          </div>
        </div>
        <div class="row">
          <div>
            <label for="refill-slot-id">slot_id</label>
            <input id="refill-slot-id" name="refill-slot-id" type="number" value="1">
          </div>
          <div>
            <label for="refill-quantity">quantity</label>
            <input id="refill-quantity" name="refill-quantity" type="number" value="5" min="0">
          </div>
        </div>
        <div class="row">
          <div>
            <label for="refill-mode">mode</label>
            <select id="refill-mode" name="refill-mode">
              <option value="set" selected>set</option>
              <option value="add">add</option>
            </select>
          </div>
          <div>
            <label for="refill-session-id">session_id</label>
            <input id="refill-session-id" name="refill-session-id" type="number" placeholder="Empty sends null">
          </div>
        </div>
        <div class="actions">
          <button type="button" id="refill-run">Execute Refill</button>
        </div>
        <pre id="refill-output">Ready.</pre>
      </article>

      <article class="card">
        <h2>Recovery Basics</h2>
        <p>Run scan, inspect a case, prepare manual resolution, then apply a decision.</p>
        <div class="row">
          <div>
            <label for="recovery-case-id">recovery_case_id</label>
            <input id="recovery-case-id" name="recovery-case-id" type="number" value="1">
          </div>
          <div>
            <label for="recovery-operator-user-id">operator_user_id</label>
            <input id="recovery-operator-user-id" name="recovery-operator-user-id" type="number" value="2">
          </div>
        </div>
        <div class="row">
          <div>
            <label for="recovery-decision">decision</label>
            <select id="recovery-decision" name="recovery-decision">
              <option value="close_case" selected>close_case</option>
            </select>
          </div>
          <div></div>
        </div>
        <div class="row single">
          <div>
            <label for="recovery-comment">comment</label>
            <textarea id="recovery-comment" name="recovery-comment">Operator verified physical state</textarea>
          </div>
        </div>
        <div class="actions">
          <button type="button" id="recovery-scan">Run Recovery Scan</button>
          <button type="button" class="secondary" id="recovery-case">Read Case</button>
          <button type="button" class="secondary" id="recovery-prepare">Prepare Resolution</button>
          <button type="button" id="recovery-apply">Apply Resolution</button>
        </div>
        <pre id="recovery-output">Ready.</pre>
        <div class="hint">The scan result includes case IDs. Copy or keep the seeded default <code>1</code> when using the demo seed.</div>
      </article>
    </section>
  </main>

  <script>
    function value(id) {
      return document.getElementById(id).value.trim();
    }

    function intOrNull(id) {
      const raw = value(id);
      if (raw === "") {
        return null;
      }
      const parsed = Number.parseInt(raw, 10);
      return Number.isNaN(parsed) ? null : parsed;
    }

    function intOrRequired(id) {
      const parsed = intOrNull(id);
      if (parsed === null) {
        throw new Error("Missing required numeric field: " + id);
      }
      return parsed;
    }

    function renderOutput(targetId, payload, ok) {
      const panel = document.getElementById(targetId);
      panel.textContent = JSON.stringify(payload, null, 2);
      panel.className = ok ? "ok" : "error";
    }

    async function apiRequest(targetId, method, url, body) {
      const options = {
        method: method,
        headers: { "Accept": "application/json" }
      };
      if (body !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
      }

      try {
        const response = await fetch(url, options);
        const text = await response.text();
        const payload = text ? JSON.parse(text) : {};
        renderOutput(targetId, payload, response.ok);
        return { response: response, payload: payload };
      } catch (error) {
        renderOutput(targetId, { error: "request_failed", detail: String(error) }, false);
        return null;
      }
    }

    async function refreshStatus() {
      const healthStatus = document.getElementById("health-status");
      const readinessStatus = document.getElementById("readiness-status");
      healthStatus.textContent = "Loading...";
      readinessStatus.textContent = "Loading...";

      const health = await apiRequest("status-output", "GET", "/health");
      if (health && health.response.ok) {
        healthStatus.textContent = "ok";
        healthStatus.className = "ok";
      } else {
        healthStatus.textContent = "error";
        healthStatus.className = "error";
      }

      const readiness = await apiRequest("status-output", "GET", "/readiness");
      if (readiness && readiness.response.ok) {
        readinessStatus.textContent = readiness.payload.readiness_status || "ready";
        readinessStatus.className = "ok";
      } else {
        readinessStatus.textContent = "error";
        readinessStatus.className = "error";
      }
    }

    document.getElementById("refresh-status").addEventListener("click", refreshStatus);

    document.getElementById("auth-by-id").addEventListener("click", async function () {
      await apiRequest("auth-output", "POST", "/auth/resolve", {
        user_id: intOrRequired("auth-user-id")
      });
    });

    document.getElementById("auth-by-code").addEventListener("click", async function () {
      await apiRequest("auth-output", "POST", "/auth/resolve", {
        user_code: value("auth-user-code")
      });
    });

    document.getElementById("inventory-run").addEventListener("click", async function () {
      const slotId = intOrRequired("inventory-slot-id");
      const itemId = intOrRequired("inventory-item-id");
      await apiRequest("inventory-output", "GET", "/inventory/" + slotId + "/" + itemId);
    });

    document.getElementById("dispense-run").addEventListener("click", async function () {
      await apiRequest("dispense-output", "POST", "/operations/dispense", {
        user_id: intOrRequired("dispense-user-id"),
        item_id: intOrRequired("dispense-item-id"),
        slot_id: intOrRequired("dispense-slot-id"),
        quantity: intOrRequired("dispense-quantity"),
        session_id: intOrNull("dispense-session-id")
      });
    });

    document.getElementById("return-run").addEventListener("click", async function () {
      await apiRequest("return-output", "POST", "/operations/return", {
        user_id: intOrRequired("return-user-id"),
        item_id: intOrRequired("return-item-id"),
        slot_id: intOrNull("return-slot-id"),
        quantity: intOrRequired("return-quantity"),
        session_id: intOrNull("return-session-id")
      });
    });

    document.getElementById("refill-run").addEventListener("click", async function () {
      await apiRequest("refill-output", "POST", "/operations/refill", {
        operator_user_id: intOrRequired("refill-operator-user-id"),
        item_id: intOrRequired("refill-item-id"),
        slot_id: intOrRequired("refill-slot-id"),
        quantity: intOrRequired("refill-quantity"),
        mode: value("refill-mode"),
        session_id: intOrNull("refill-session-id")
      });
    });

    document.getElementById("recovery-scan").addEventListener("click", async function () {
      await apiRequest("recovery-output", "POST", "/recovery/scan");
    });

    document.getElementById("recovery-case").addEventListener("click", async function () {
      const caseId = intOrRequired("recovery-case-id");
      await apiRequest("recovery-output", "GET", "/recovery/cases/" + caseId);
    });

    document.getElementById("recovery-prepare").addEventListener("click", async function () {
      const caseId = intOrRequired("recovery-case-id");
      await apiRequest("recovery-output", "GET", "/recovery/cases/" + caseId + "/manual-resolution");
    });

    document.getElementById("recovery-apply").addEventListener("click", async function () {
      const caseId = intOrRequired("recovery-case-id");
      await apiRequest("recovery-output", "POST", "/recovery/cases/" + caseId + "/manual-resolution", {
        operator_user_id: intOrRequired("recovery-operator-user-id"),
        decision: value("recovery-decision"),
        comment: value("recovery-comment") || null
      });
    });

    refreshStatus();
  </script>
</body>
</html>
"""
