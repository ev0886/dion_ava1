(function () {
  const config = window.DION_ADMIN_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    statusTitle: document.getElementById("status-title"),
    statusMessage: document.getElementById("status-message"),
    refreshButton: document.getElementById("refresh-button"),
    userTableBody: document.getElementById("user-table-body"),
    importFile: document.getElementById("import-file"),
    importTextarea: document.getElementById("import-textarea"),
    importButton: document.getElementById("import-button"),
    importResult: document.getElementById("import-result"),
    importResultTitle: document.getElementById("import-result-title"),
    importResultMessage: document.getElementById("import-result-message"),
  };

  const state = {
    users: [],
    isLoading: false,
    isImporting: false,
    savingUserIds: new Set(),
  };

  function setStatus(kind, title, message) {
    elements.statusPanel.className = "status-panel";
    if (kind) {
      elements.statusPanel.classList.add("status-" + kind);
    }
    elements.statusTitle.textContent = title;
    elements.statusMessage.textContent = message;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setImportResult(kind, title, message) {
    elements.importResult.className = "import-result";
    if (kind) {
      elements.importResult.classList.add("import-result-" + kind);
    }
    elements.importResultTitle.textContent = title;
    elements.importResultMessage.textContent = message;
  }

  function userRowMarkup(user) {
    const saveDisabled = state.isLoading || state.savingUserIds.has(user.user_id) ? "disabled" : "";
    const policyOptions = config.supportedPolicies
      .map(function (policy) {
        const selected = user.dispense_restriction_policy === policy ? "selected" : "";
        return '<option value="' + escapeHtml(policy) + '" ' + selected + ">" + escapeHtml(policy) + "</option>";
      })
      .join("");

    return (
      '<tr data-user-id="' +
      String(user.user_id) +
      '">' +
      "<td>" +
      String(user.user_id) +
      "</td>" +
      "<td>" +
      escapeHtml(user.user_code) +
      "</td>" +
      "<td>" +
      escapeHtml(user.full_name) +
      "</td>" +
      '<td><span class="status-chip">' +
      escapeHtml(user.status) +
      "</span></td>" +
      '<td><span class="active-chip">' +
      (user.is_active ? "active" : "inactive") +
      "</span></td>" +
      "<td>" +
      escapeHtml(user.role_code || "n/a") +
      "</td>" +
      "<td>" +
      '<input class="inline-input" name="rfid_uid" type="text" value="' +
      escapeHtml(user.rfid_uid || "") +
      '" placeholder="Unassigned">' +
      '<div class="row-note">Leave blank to clear assignment.</div>' +
      "</td>" +
      "<td>" +
      '<select class="inline-select" name="dispense_restriction_policy">' +
      policyOptions +
      "</select>" +
      "</td>" +
      "<td>" +
      '<button class="save-button" type="button" ' +
      saveDisabled +
      ">Save</button>" +
      "</td>" +
      "</tr>"
    );
  }

  function renderUsers() {
    if (!state.users.length) {
      elements.userTableBody.innerHTML =
        '<tr><td colspan="9" class="placeholder-cell">No users found in the current runtime database.</td></tr>';
      return;
    }

    elements.userTableBody.innerHTML = state.users.map(userRowMarkup).join("");
    elements.userTableBody.querySelectorAll(".save-button").forEach(function (button) {
      button.addEventListener("click", function () {
        const row = button.closest("tr");
        if (!row) {
          return;
        }
        const userId = Number(row.dataset.userId);
        void saveRow(userId, row);
      });
    });
  }

  async function readJson(url, options) {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
      },
      ...options,
    });
    const payload = await response.json();
    return { response, payload };
  }

  function syncControls() {
    elements.refreshButton.disabled = state.isLoading;
    elements.importButton.disabled = state.isLoading || state.isImporting;
    elements.importFile.disabled = state.isImporting;
    elements.importTextarea.disabled = state.isImporting;
    const saveButtons = elements.userTableBody.querySelectorAll(".save-button");
    saveButtons.forEach(function (button) {
      const row = button.closest("tr");
      const userId = row ? Number(row.dataset.userId) : 0;
      button.disabled = state.isLoading || state.savingUserIds.has(userId);
    });
  }

  async function readImportCsvText() {
    const file = elements.importFile.files && elements.importFile.files[0];
    if (file) {
      return await file.text();
    }
    return elements.importTextarea.value;
  }

  function formatImportSummary(result) {
    return (
      "Created: " +
      String(result.created_count) +
      ", updated: " +
      String(result.updated_count) +
      ", total rows: " +
      String(result.total_rows) +
      "."
    );
  }

  async function loadUsers() {
    state.isLoading = true;
    syncControls();
    setStatus("", "Loading", "Refreshing user records from the local backend.");

    try {
      const { response, payload } = await readJson(config.listUsersEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "User list request failed.");
      }
      state.users = Array.isArray(payload.users) ? payload.users : [];
      renderUsers();
      setStatus("success", "Ready", "User records loaded. Edit RFID UID or dispense policy and save per row.");
    } catch (error) {
      state.users = [];
      renderUsers();
      setStatus("error", "Load Failed", String(error));
    } finally {
      state.isLoading = false;
      syncControls();
    }
  }

  async function saveRow(userId, row) {
    state.savingUserIds.add(userId);
    syncControls();
    setStatus("", "Saving", "Saving changes for user " + String(userId) + ".");

    const rfidInput = row.querySelector('input[name="rfid_uid"]');
    const policySelect = row.querySelector('select[name="dispense_restriction_policy"]');

    try {
      const { response, payload } = await readJson(config.updateUserEndpointBase + "/" + String(userId), {
        method: "PUT",
        body: JSON.stringify({
          rfid_uid: rfidInput ? rfidInput.value : "",
          dispense_restriction_policy: policySelect ? policySelect.value : "unlimited",
        }),
      });
      if (!response.ok) {
        throw new Error(payload.detail || "Save request failed.");
      }

      const savedUser = payload.user;
      state.users = state.users.map(function (user) {
        return user.user_id === userId ? savedUser : user;
      });
      renderUsers();
      setStatus(
        "success",
        "Saved",
        "User " + String(userId) + " updated. RFID UID and dispense policy are now stored in the local database."
      );
    } catch (error) {
      setStatus("error", "Save Failed", String(error));
    } finally {
      state.savingUserIds.delete(userId);
      syncControls();
    }
  }

  async function importUsers() {
    state.isImporting = true;
    syncControls();
    setStatus("", "Importing", "Submitting users CSV to the local backend.");
    setImportResult("", "Import In Progress", "Waiting for backend validation and import result.");

    try {
      const csvText = await readImportCsvText();
      const response = await fetch(config.importUsersEndpoint, {
        method: "POST",
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
        },
        body: csvText,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.error || "Import request failed.");
      }

      const result = payload.result || {};
      setImportResult("success", "Import Completed", formatImportSummary(result));
      setStatus("success", "Import Completed", "Users CSV processed successfully. Refreshing the list.");
      await loadUsers();
    } catch (error) {
      setImportResult("error", "Import Failed", String(error));
      setStatus("error", "Import Failed", String(error));
    } finally {
      state.isImporting = false;
      syncControls();
    }
  }

  elements.refreshButton.addEventListener("click", function () {
    void loadUsers();
  });
  elements.importButton.addEventListener("click", function () {
    void importUsers();
  });

  void loadUsers();
})();
