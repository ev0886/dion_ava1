(function () {
  const config = window.DION_ADMIN_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    statusTitle: document.getElementById("status-title"),
    statusMessage: document.getElementById("status-message"),
    refreshButton: document.getElementById("refresh-button"),
    userTableBody: document.getElementById("user-table-body"),
  };

  const state = {
    users: [],
    isLoading: false,
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
    const saveButtons = elements.userTableBody.querySelectorAll(".save-button");
    saveButtons.forEach(function (button) {
      const row = button.closest("tr");
      const userId = row ? Number(row.dataset.userId) : 0;
      button.disabled = state.isLoading || state.savingUserIds.has(userId);
    });
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

  elements.refreshButton.addEventListener("click", function () {
    void loadUsers();
  });

  void loadUsers();
})();
