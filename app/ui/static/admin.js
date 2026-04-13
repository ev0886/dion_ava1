(function () {
  const config = window.DION_ADMIN_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    statusTitle: document.getElementById("status-title"),
    statusMessage: document.getElementById("status-message"),
    systemHealthStatus: document.getElementById("system-health-status"),
    systemReadinessStatus: document.getElementById("system-readiness-status"),
    systemHardwareProvider: document.getElementById("system-hardware-provider"),
    systemAppEnvironment: document.getElementById("system-app-environment"),
    systemAppName: document.getElementById("system-app-name"),
    systemApiBind: document.getElementById("system-api-bind"),
    refreshButton: document.getElementById("refresh-button"),
    userTableBody: document.getElementById("user-table-body"),
    problemOperationsTableBody: document.getElementById("problem-operations-table-body"),
    operationsTableBody: document.getElementById("operations-table-body"),
    importFile: document.getElementById("import-file"),
    importTextarea: document.getElementById("import-textarea"),
    loadExampleButton: document.getElementById("load-example-button"),
    exportUsersLink: document.getElementById("export-users-link"),
    downloadExampleLink: document.getElementById("download-example-link"),
    importButton: document.getElementById("import-button"),
    importResult: document.getElementById("import-result"),
    importResultTitle: document.getElementById("import-result-title"),
    importResultMessage: document.getElementById("import-result-message"),
  };

  const state = {
    users: [],
    problemOperations: [],
    operations: [],
    systemStatus: null,
    isLoading: false,
    isImporting: false,
    savingUserIds: new Set(),
  };

  const displayLabels = {
    system: {
      ok: "OK",
      degraded: "\u041e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u043d\u0430\u044f \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u044c",
      ready: "\u0413\u043e\u0442\u043e\u0432\u043e",
      not_ready: "\u041d\u0435 \u0433\u043e\u0442\u043e\u0432\u043e",
      real: "\u0420\u0435\u0430\u043b\u044c\u043d\u044b\u0439",
      "stub-real": "Stub-real",
      mock: "Mock",
      development: "\u0420\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0430",
      "production-like": "Production-like",
    },
    operationType: {
      dispense: "\u0412\u044b\u0434\u0430\u0447\u0430",
      return: "\u0412\u043e\u0437\u0432\u0440\u0430\u0442",
      refill_item: "\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435",
    },
    operationState: {
      completed: "\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
      failed: "\u041e\u0448\u0438\u0431\u043a\u0430",
      recovery_required: "\u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u0435",
    },
    policy: {
      unlimited: "\u0411\u0435\u0437 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439",
      once_per_day: "\u041e\u0434\u0438\u043d \u0440\u0430\u0437 \u0432 \u0434\u0435\u043d\u044c",
    },
    userStatus: {
      active: "\u0410\u043a\u0442\u0438\u0432\u0435\u043d",
      inactive: "\u041d\u0435\u0430\u043a\u0442\u0438\u0432\u0435\u043d",
      blocked: "\u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d",
    },
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

  function formatSystemValue(value) {
    if (value === null || value === undefined || value === "") {
      return "n/a";
    }
    return String(value);
  }

  function getDisplayLabel(group, value) {
    if (value === null || value === undefined || value === "") {
      return "n/a";
    }
    const rawValue = String(value);
    return displayLabels[group] && displayLabels[group][rawValue]
      ? displayLabels[group][rawValue]
      : rawValue;
  }

  function renderSystemStatus() {
    const systemStatus = state.systemStatus;
    if (!systemStatus) {
      elements.systemHealthStatus.textContent = "n/a";
      elements.systemReadinessStatus.textContent = "n/a";
      elements.systemHardwareProvider.textContent = "n/a";
      elements.systemAppEnvironment.textContent = "n/a";
      elements.systemAppName.textContent = "n/a";
      elements.systemApiBind.textContent = "n/a";
      return;
    }

    elements.systemHealthStatus.textContent = getDisplayLabel("system", systemStatus.health_status);
    elements.systemReadinessStatus.textContent = getDisplayLabel("system", systemStatus.readiness_status);
    elements.systemHardwareProvider.textContent = getDisplayLabel("system", systemStatus.hardware_provider);
    elements.systemAppEnvironment.textContent = getDisplayLabel("system", systemStatus.app_environment);
    elements.systemAppName.textContent = formatSystemValue(systemStatus.app_name);
    elements.systemApiBind.textContent =
      formatSystemValue(systemStatus.api_host) + ":" + formatSystemValue(systemStatus.api_port);
  }

  function userRowMarkup(user) {
    const saveDisabled = state.isLoading || state.savingUserIds.has(user.user_id) ? "disabled" : "";
    const policyOptions = config.supportedPolicies
      .map(function (policy) {
        const selected = user.dispense_restriction_policy === policy ? "selected" : "";
        return (
          '<option value="' +
          escapeHtml(policy) +
          '" ' +
          selected +
          ">" +
          escapeHtml(getDisplayLabel("policy", policy)) +
          "</option>"
        );
      })
      .join("");
    const activeOptions = [
      '<option value="true" ' +
        (user.is_active ? "selected" : "") +
        ">\u0410\u043a\u0442\u0438\u0432\u0435\u043d</option>",
      '<option value="false" ' +
        (!user.is_active ? "selected" : "") +
        ">\u041d\u0435\u0430\u043a\u0442\u0438\u0432\u0435\u043d</option>",
    ].join("");

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
      escapeHtml(getDisplayLabel("userStatus", user.status)) +
      "</span></td>" +
      '<td><span class="active-chip">' +
      (user.is_active ? "активен" : "неактивен") +
      "</span>" +
      '<select class="inline-select" name="is_active">' +
      activeOptions +
      "</select></td>" +
      "<td>" +
      escapeHtml(user.role_code || "n/a") +
      "</td>" +
      "<td>" +
      '<input class="inline-input" name="rfid_uid" type="text" value="' +
      escapeHtml(user.rfid_uid || "") +
      '" placeholder="Не назначен">' +
      '<div class="row-note">Оставьте пустым, чтобы снять привязку.</div>' +
      "</td>" +
      "<td>" +
      '<select class="inline-select" name="dispense_restriction_policy">' +
      policyOptions +
      "</select>" +
      "</td>" +
      "<td>" +
      '<button class="save-button" type="button" ' +
      saveDisabled +
      ">Сохранить</button>" +
      "</td>" +
      "</tr>"
    );
  }

  function renderUsers() {
    if (!state.users.length) {
      elements.userTableBody.innerHTML =
        '<tr><td colspan="9" class="placeholder-cell">В текущей runtime-базе пользователи не найдены.</td></tr>';
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

  function formatDateTime(value) {
    if (!value) {
      return "n/a";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString("ru-RU", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  function buildUserLabel(operation) {
    const parts = [];
    if (operation.user_code) {
      parts.push(operation.user_code);
    }
    if (operation.user_full_name) {
      parts.push(operation.user_full_name);
    }
    return parts.length ? parts.join(" / ") : "n/a";
  }

  function operationRowMarkup(operation) {
    const quantity =
      operation.quantity === null || operation.quantity === undefined ? "n/a" : String(operation.quantity);

    return (
      "<tr>" +
      "<td>" +
      escapeHtml(formatDateTime(operation.started_at)) +
      "</td>" +
      "<td>" +
      escapeHtml(getDisplayLabel("operationType", operation.operation_type)) +
      "</td>" +
      '<td><span class="status-chip">' +
      escapeHtml(getDisplayLabel("operationState", operation.operation_state)) +
      "</span></td>" +
      "<td>" +
      escapeHtml(buildUserLabel(operation)) +
      "</td>" +
      "<td>" +
      escapeHtml(operation.item_name || "n/a") +
      "</td>" +
      "<td>" +
      escapeHtml(quantity) +
      "</td>" +
      "<td>" +
      escapeHtml(operation.slot_code || "n/a") +
      "</td>" +
      "</tr>"
    );
  }

  function renderOperations() {
    if (!state.operations.length) {
      elements.operationsTableBody.innerHTML =
        '<tr><td colspan="7" class="placeholder-cell">Последние операции пока не найдены.</td></tr>';
      return;
    }

    elements.operationsTableBody.innerHTML = state.operations.map(operationRowMarkup).join("");
  }

  function renderProblemOperations() {
    if (!state.problemOperations.length) {
      elements.problemOperationsTableBody.innerHTML =
        '<tr><td colspan="7" class="placeholder-cell">Проблемные операции не найдены.</td></tr>';
      return;
    }

    elements.problemOperationsTableBody.innerHTML = state.problemOperations.map(operationRowMarkup).join("");
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
    elements.loadExampleButton.disabled = state.isImporting;
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

  function loadExampleCsv() {
    elements.importTextarea.value = config.importExampleCsvText;
    elements.importFile.value = "";
    setImportResult("", "Пример загружен", "Образец CSV вставлен в текстовое поле и готов к редактированию.");
  }

  function formatImportSummary(result) {
    return (
      "Создано: " +
      String(result.created_count) +
      ", обновлено: " +
      String(result.updated_count) +
      ", всего строк: " +
      String(result.total_rows) +
      "."
    );
  }

  async function loadUsers() {
    try {
      const { response, payload } = await readJson(config.listUsersEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось получить список пользователей.");
      }
      state.users = Array.isArray(payload.users) ? payload.users : [];
      renderUsers();
    } catch (error) {
      state.users = [];
      renderUsers();
      throw error;
    }
  }

  async function loadSystemStatus() {
    try {
      const { response, payload } = await readJson(config.systemStatusEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to load system status.");
      }
      state.systemStatus = payload;
      renderSystemStatus();
    } catch (error) {
      state.systemStatus = null;
      renderSystemStatus();
      throw error;
    }
  }

  async function loadRecentOperations() {
    try {
      const { response, payload } = await readJson(config.recentOperationsEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось получить список последних операций.");
      }
      state.operations = Array.isArray(payload.operations) ? payload.operations : [];
      renderOperations();
    } catch (error) {
      state.operations = [];
      renderOperations();
      throw error;
    }
  }

  async function loadProblemOperations() {
    try {
      const { response, payload } = await readJson(config.problemOperationsEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to load problem operations.");
      }
      state.problemOperations = Array.isArray(payload.operations) ? payload.operations : [];
      renderProblemOperations();
    } catch (error) {
      state.problemOperations = [];
      renderProblemOperations();
      throw error;
    }
  }

  async function loadAdminData() {
    state.isLoading = true;
    syncControls();
    setStatus("", "Загрузка", "Обновление пользователей и последних операций из локального backend.");

    try {
      await Promise.all([loadSystemStatus(), loadUsers(), loadProblemOperations(), loadRecentOperations()]);
      setStatus(
        "success",
        "Готово",
        "Пользователи и последние операции загружены. Измените RFID UID или политику выдачи и сохраните нужную строку."
      );
    } catch (error) {
      setStatus("error", "Ошибка загрузки", String(error));
    } finally {
      state.isLoading = false;
      syncControls();
    }
  }

  async function saveRow(userId, row) {
    state.savingUserIds.add(userId);
    syncControls();
    setStatus("", "Сохранение", "Сохранение изменений для пользователя " + String(userId) + ".");

    const rfidInput = row.querySelector('input[name="rfid_uid"]');
    const activeSelect = row.querySelector('select[name="is_active"]');
    const policySelect = row.querySelector('select[name="dispense_restriction_policy"]');

    try {
      const { response, payload } = await readJson(config.updateUserEndpointBase + "/" + String(userId), {
        method: "PUT",
        body: JSON.stringify({
          rfid_uid: rfidInput ? rfidInput.value : "",
          is_active: activeSelect ? activeSelect.value === "true" : true,
          dispense_restriction_policy: policySelect ? policySelect.value : "unlimited",
        }),
      });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось сохранить изменения.");
      }

      const savedUser = payload.user;
      state.users = state.users.map(function (user) {
        return user.user_id === userId ? savedUser : user;
      });
      renderUsers();
      setStatus(
        "success",
        "Сохранено",
        "Пользователь " + String(userId) + " обновлен. RFID UID и политика выдачи сохранены в локальной базе."
      );
    } catch (error) {
      setStatus("error", "Ошибка сохранения", String(error));
    } finally {
      state.savingUserIds.delete(userId);
      syncControls();
    }
  }

  async function importUsers() {
    state.isImporting = true;
    syncControls();
    setStatus("", "Импорт", "Отправка CSV пользователей в локальный backend.");
    setImportResult("", "Импорт выполняется", "Ожидание валидации backend и результата импорта.");

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
        throw new Error(payload.detail || payload.error || "Не удалось выполнить импорт.");
      }

      const result = payload.result || {};
      setImportResult("success", "Импорт завершен", formatImportSummary(result));
      setStatus("success", "Импорт завершен", "CSV пользователей успешно обработан. Обновляю список.");
      await loadAdminData();
    } catch (error) {
      setImportResult("error", "Ошибка импорта", String(error));
      setStatus("error", "Ошибка импорта", String(error));
    } finally {
      state.isImporting = false;
      syncControls();
    }
  }

  elements.refreshButton.addEventListener("click", function () {
    void loadAdminData();
  });
  elements.loadExampleButton.addEventListener("click", function () {
    loadExampleCsv();
  });
  if (elements.downloadExampleLink && config.importExampleCsvAssetUrl) {
    elements.downloadExampleLink.href = config.importExampleCsvAssetUrl;
  }
  if (elements.exportUsersLink && config.exportUsersEndpoint) {
    elements.exportUsersLink.href = config.exportUsersEndpoint;
  }
  elements.importButton.addEventListener("click", function () {
    void importUsers();
  });

  renderSystemStatus();
  renderProblemOperations();
  renderOperations();
  void loadAdminData();
})();
