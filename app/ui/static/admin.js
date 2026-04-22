(function () {
  const config = window.DION_ADMIN_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    statusTitle: document.getElementById("status-title"),
    statusMessage: document.getElementById("status-message"),
    systemApiStatus: document.getElementById("system-api-status"),
    systemHardwareStatus: document.getElementById("system-hardware-status"),
    systemHardwareMode: document.getElementById("system-hardware-mode"),
    systemOpenCells: document.getElementById("system-open-cells"),
    systemCheckedAt: document.getElementById("system-checked-at"),
    refreshButton: document.getElementById("refresh-button"),
    userCreateCode: document.getElementById("user-create-code"),
    userCreateName: document.getElementById("user-create-name"),
    userCreateRole: document.getElementById("user-create-role"),
    userCreateRfid: document.getElementById("user-create-rfid"),
    userCreatePolicy: document.getElementById("user-create-policy"),
    userCreateActive: document.getElementById("user-create-active"),
    userCreateButton: document.getElementById("user-create-button"),
    nomenclatureCreateName: document.getElementById("nomenclature-create-name"),
    nomenclatureCreateButton: document.getElementById("nomenclature-create-button"),
    nomenclatureTableBody: document.getElementById("nomenclature-table-body"),
    userTableBody: document.getElementById("user-table-body"),
    problemOperationsTableBody: document.getElementById("problem-operations-table-body"),
    operationsTableBody: document.getElementById("operations-table-body"),
    operationsExportDateFrom: document.getElementById("operations-export-date-from"),
    operationsExportDateTo: document.getElementById("operations-export-date-to"),
    operationsExportButton: document.getElementById("operations-export-button"),
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
    nomenclature: [],
    problemOperations: [],
    operations: [],
    systemStatus: null,
    isLoading: false,
    isExportingOperations: false,
    isImporting: false,
    savingUserIds: new Set(),
    savingNomenclatureIds: new Set(),
    isCreatingNomenclature: false,
    isCreatingUser: false,
  };

  const displayLabels = {
    system: {
      available: "\u041e\u043d\u043b\u0430\u0439\u043d",
      unavailable: "\u041d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e",
      ready: "\u0413\u043e\u0442\u043e\u0432\u043e",
      error: "\u0415\u0441\u0442\u044c \u043e\u0448\u0438\u0431\u043a\u0438",
      real: "\u0420\u0435\u0430\u043b\u044c\u043d\u044b\u0439",
      mock: "Mock",
      no: "\u041d\u0435\u0442",
      yes: "\u0415\u0441\u0442\u044c",
    },
    operationType: {
      dispense: "\u0412\u044b\u0434\u0430\u0447\u0430",
      return: "\u0412\u043e\u0437\u0432\u0440\u0430\u0442",
      refill_item: "\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435",
    },
    operationState: {
      completed: "\u0417\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
      failed: "\u041e\u0448\u0438\u0431\u043a\u0430",
      recovery_required: "\u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044f \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430",
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
      elements.systemApiStatus.textContent = getDisplayLabel("system", "unavailable");
      elements.systemHardwareStatus.textContent = "n/a";
      elements.systemHardwareMode.textContent = "n/a";
      elements.systemOpenCells.textContent = "n/a";
      elements.systemCheckedAt.textContent = "n/a";
      return;
    }

    elements.systemApiStatus.textContent = getDisplayLabel("system", systemStatus.api_available ? "available" : "unavailable");
    elements.systemHardwareStatus.textContent = getDisplayLabel("system", systemStatus.hardware_status);
    elements.systemHardwareMode.textContent = getDisplayLabel("system", systemStatus.hardware_mode);
    elements.systemOpenCells.textContent = getDisplayLabel("system", systemStatus.open_cells ? "yes" : "no");
    elements.systemCheckedAt.textContent = formatDateTime(systemStatus.checked_at);
  }

  function nomenclatureRowMarkup(entry) {
    const saveDisabled = state.isLoading || state.savingNomenclatureIds.has(entry.id) ? "disabled" : "";
    const toggleLabel = entry.is_active ? "Активна" : "Неактивна";
    const toggleAction = entry.is_active ? "deactivate" : "activate";
    const toggleButtonLabel = entry.is_active ? "Деактивировать" : "Активировать";

    return (
      '<tr data-nomenclature-id="' +
      String(entry.id) +
      '">' +
      "<td>" +
      String(entry.id) +
      "</td>" +
      "<td>" +
      '<input class="inline-input" name="name" type="text" value="' +
      escapeHtml(entry.name) +
      '" placeholder="Наименование">' +
      "</td>" +
      '<td><span class="status-chip">' +
      escapeHtml(toggleLabel) +
      "</span></td>" +
      "<td>" +
      '<button class="save-button nomenclature-save-button" type="button" ' +
      saveDisabled +
      ">Сохранить</button>" +
      "</td>" +
      "<td>" +
      '<div class="nomenclature-action-row">' +
      '<button class="secondary-button nomenclature-toggle-button" data-action="' +
      toggleAction +
      '" type="button" ' +
      saveDisabled +
      ">" +
      toggleButtonLabel +
      "</button>" +
      "</div>" +
      "</td>" +
      "</tr>"
    );
  }

  function renderNomenclature() {
    if (!state.nomenclature.length) {
      elements.nomenclatureTableBody.innerHTML =
        '<tr><td colspan="5" class="placeholder-cell">Справочник номенклатуры пока пуст.</td></tr>';
      return;
    }

    elements.nomenclatureTableBody.innerHTML = state.nomenclature.map(nomenclatureRowMarkup).join("");
    elements.nomenclatureTableBody.querySelectorAll(".nomenclature-save-button").forEach(function (button) {
      button.addEventListener("click", function () {
        const row = button.closest("tr");
        if (!row) {
          return;
        }
        const nomenclatureId = Number(row.dataset.nomenclatureId);
        void saveNomenclature(nomenclatureId, row);
      });
    });
    elements.nomenclatureTableBody.querySelectorAll(".nomenclature-toggle-button").forEach(function (button) {
      button.addEventListener("click", function () {
        const row = button.closest("tr");
        if (!row) {
          return;
        }
        const nomenclatureId = Number(row.dataset.nomenclatureId);
        const action = button.dataset.action || "";
        void toggleNomenclature(nomenclatureId, action);
      });
    });
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
      '<td><select class="inline-select" name="is_active">' +
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
      escapeHtml(operation.cell_number === null || operation.cell_number === undefined ? "n/a" : String(operation.cell_number)) +
      "</td>" +
      "</tr>"
    );
  }

  function renderOperations() {
    if (!state.operations.length) {
      elements.operationsTableBody.innerHTML =
        '<tr><td colspan="6" class="placeholder-cell">Последние операции пока не найдены.</td></tr>';
      return;
    }

    elements.operationsTableBody.innerHTML = state.operations.map(operationRowMarkup).join("");
  }

  function renderProblemOperations() {
    if (!state.problemOperations.length) {
      elements.problemOperationsTableBody.innerHTML =
        '<tr><td colspan="6" class="placeholder-cell">Проблемные операции не найдены.</td></tr>';
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
    elements.userCreateButton.disabled = state.isLoading || state.isCreatingUser;
    elements.userCreateCode.disabled = state.isCreatingUser;
    elements.userCreateName.disabled = state.isCreatingUser;
    elements.userCreateRole.disabled = state.isCreatingUser;
    elements.userCreateRfid.disabled = state.isCreatingUser;
    elements.userCreatePolicy.disabled = state.isCreatingUser;
    elements.userCreateActive.disabled = state.isCreatingUser;
    elements.nomenclatureCreateButton.disabled = state.isLoading || state.isCreatingNomenclature;
    elements.nomenclatureCreateName.disabled = state.isCreatingNomenclature;
    elements.operationsExportButton.disabled = state.isLoading || state.isExportingOperations;
    elements.operationsExportDateFrom.disabled = state.isExportingOperations;
    elements.operationsExportDateTo.disabled = state.isExportingOperations;
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
    const nomenclatureButtons = elements.nomenclatureTableBody.querySelectorAll("button");
    nomenclatureButtons.forEach(function (button) {
      const row = button.closest("tr");
      const nomenclatureId = row ? Number(row.dataset.nomenclatureId) : 0;
      button.disabled = state.isLoading || state.savingNomenclatureIds.has(nomenclatureId);
    });
  }

  function buildOperationsExportUrl() {
    const dateFrom = elements.operationsExportDateFrom.value;
    const dateTo = elements.operationsExportDateTo.value;
    if (!dateFrom || !dateTo) {
      throw new Error("Укажите даты «с» и «по» для экспорта CSV.");
    }

    const params = new URLSearchParams({
      date_from: dateFrom,
      date_to: dateTo,
    });
    return config.exportOperationsEndpoint + "?" + params.toString();
  }

  function downloadFile(url) {
    const link = document.createElement("a");
    link.href = url;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
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

  async function loadNomenclature() {
    try {
      const { response, payload } = await readJson(config.listNomenclatureEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось получить список номенклатуры.");
      }
      state.nomenclature = Array.isArray(payload.nomenclature) ? payload.nomenclature : [];
      renderNomenclature();
    } catch (error) {
      state.nomenclature = [];
      renderNomenclature();
      throw error;
    }
  }

  async function loadSystemStatus() {
    try {
      const { response, payload } = await readJson(config.systemStatusEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось загрузить статус системы.");
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
        throw new Error(payload.detail || "Не удалось загрузить проблемные операции.");
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
      await Promise.all([loadSystemStatus(), loadUsers(), loadNomenclature(), loadProblemOperations(), loadRecentOperations()]);
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

  async function createUser() {
    state.isCreatingUser = true;
    syncControls();
    setStatus("", "Пользователи", "Создание нового пользователя.");

    try {
      const { response, payload } = await readJson(config.createUserEndpoint, {
        method: "POST",
        body: JSON.stringify({
          user_code: elements.userCreateCode.value,
          full_name: elements.userCreateName.value,
          role_code: elements.userCreateRole.value,
          rfid_uid: elements.userCreateRfid.value,
          dispense_restriction_policy: elements.userCreatePolicy.value,
          is_active: elements.userCreateActive.value === "true",
        }),
      });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось создать пользователя.");
      }

      state.users.push(payload.user);
      state.users.sort(function (left, right) {
        return Number(left.user_id) - Number(right.user_id);
      });
      renderUsers();
      elements.userCreateCode.value = "";
      elements.userCreateName.value = "";
      elements.userCreateRole.value = "user";
      elements.userCreateRfid.value = "";
      elements.userCreatePolicy.value = "unlimited";
      elements.userCreateActive.value = "true";
      setStatus("success", "Пользователь создан", "Новая запись добавлена в локальную базу и доступна для редактирования.");
    } catch (error) {
      setStatus("error", "Ошибка сохранения", String(error));
    } finally {
      state.isCreatingUser = false;
      syncControls();
    }
  }

  function sortNomenclature() {
    state.nomenclature.sort(function (left, right) {
      return String(left.name).localeCompare(String(right.name), "ru");
    });
  }

  async function createNomenclature() {
    state.isCreatingNomenclature = true;
    syncControls();
    setStatus("", "Номенклатура", "Создание записи справочника номенклатуры.");

    try {
      const { response, payload } = await readJson(config.createNomenclatureEndpoint, {
        method: "POST",
        body: JSON.stringify({
          name: elements.nomenclatureCreateName.value,
        }),
      });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось создать запись номенклатуры.");
      }

      const savedEntry = payload.nomenclature;
      state.nomenclature = state.nomenclature.filter(function (entry) {
        return entry.id !== savedEntry.id;
      });
      state.nomenclature.push(savedEntry);
      sortNomenclature();
      renderNomenclature();
      elements.nomenclatureCreateName.value = "";
      setStatus(
        "success",
        payload.reactivated_existing ? "Номенклатура реактивирована" : "Номенклатура создана",
        payload.reactivated_existing
          ? "Совпадающая неактивная запись найдена и повторно активирована."
          : "Новая запись номенклатуры сохранена."
      );
    } catch (error) {
      setStatus("error", "Ошибка сохранения", String(error));
    } finally {
      state.isCreatingNomenclature = false;
      syncControls();
    }
  }

  async function saveNomenclature(nomenclatureId, row) {
    state.savingNomenclatureIds.add(nomenclatureId);
    syncControls();
    setStatus("", "Номенклатура", "Сохранение имени записи " + String(nomenclatureId) + ".");

    const nameInput = row.querySelector('input[name="name"]');

    try {
      const { response, payload } = await readJson(config.updateNomenclatureEndpointBase + "/" + String(nomenclatureId), {
        method: "PUT",
        body: JSON.stringify({
          name: nameInput ? nameInput.value : "",
        }),
      });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось обновить запись номенклатуры.");
      }

      const savedEntry = payload.nomenclature;
      state.nomenclature = state.nomenclature.map(function (entry) {
        return entry.id === nomenclatureId ? savedEntry : entry;
      });
      sortNomenclature();
      renderNomenclature();
      setStatus("success", "Номенклатура сохранена", "Имя записи номенклатуры обновлено.");
    } catch (error) {
      setStatus("error", "Ошибка сохранения", String(error));
    } finally {
      state.savingNomenclatureIds.delete(nomenclatureId);
      syncControls();
    }
  }

  async function toggleNomenclature(nomenclatureId, action) {
    state.savingNomenclatureIds.add(nomenclatureId);
    syncControls();
    setStatus("", "Номенклатура", "Изменение активности записи " + String(nomenclatureId) + ".");

    try {
      const { response, payload } = await readJson(
        config.updateNomenclatureEndpointBase + "/" + String(nomenclatureId) + "/" + action,
        {
          method: "POST",
          body: JSON.stringify({}),
        }
      );
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось изменить активность записи номенклатуры.");
      }

      const savedEntry = payload.nomenclature;
      state.nomenclature = state.nomenclature.map(function (entry) {
        return entry.id === nomenclatureId ? savedEntry : entry;
      });
      sortNomenclature();
      renderNomenclature();
      setStatus(
        "success",
        "Активность обновлена",
        savedEntry.is_active ? "Запись номенклатуры активирована." : "Запись номенклатуры деактивирована."
      );
    } catch (error) {
      setStatus("error", "Ошибка сохранения", String(error));
    } finally {
      state.savingNomenclatureIds.delete(nomenclatureId);
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

  async function exportOperations() {
    state.isExportingOperations = true;
    syncControls();

    try {
      const exportUrl = buildOperationsExportUrl();
      setStatus("success", "Экспорт CSV", "Запускаю выгрузку операций за выбранный период.");
      downloadFile(exportUrl);
    } catch (error) {
      setStatus("error", "Ошибка экспорта CSV", String(error));
    } finally {
      state.isExportingOperations = false;
      syncControls();
    }
  }

  elements.refreshButton.addEventListener("click", function () {
    void loadAdminData();
  });
  elements.userCreateButton.addEventListener("click", function () {
    void createUser();
  });
  elements.nomenclatureCreateButton.addEventListener("click", function () {
    void createNomenclature();
  });
  elements.loadExampleButton.addEventListener("click", function () {
    loadExampleCsv();
  });
  elements.operationsExportButton.addEventListener("click", function () {
    void exportOperations();
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
  renderNomenclature();
  renderProblemOperations();
  renderOperations();
  void loadAdminData();
})();
