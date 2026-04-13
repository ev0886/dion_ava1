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
    loadExampleButton: document.getElementById("load-example-button"),
    downloadExampleLink: document.getElementById("download-example-link"),
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
      (user.is_active ? "активен" : "неактивен") +
      "</span></td>" +
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
    state.isLoading = true;
    syncControls();
    setStatus("", "Загрузка", "Обновление записей пользователей из локального backend.");

    try {
      const { response, payload } = await readJson(config.listUsersEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Не удалось получить список пользователей.");
      }
      state.users = Array.isArray(payload.users) ? payload.users : [];
      renderUsers();
      setStatus("success", "Готово", "Записи пользователей загружены. Измените RFID UID или политику выдачи и сохраните нужную строку.");
    } catch (error) {
      state.users = [];
      renderUsers();
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
      await loadUsers();
    } catch (error) {
      setImportResult("error", "Ошибка импорта", String(error));
      setStatus("error", "Ошибка импорта", String(error));
    } finally {
      state.isImporting = false;
      syncControls();
    }
  }

  elements.refreshButton.addEventListener("click", function () {
    void loadUsers();
  });
  elements.loadExampleButton.addEventListener("click", function () {
    loadExampleCsv();
  });
  if (elements.downloadExampleLink && config.importExampleCsvAssetUrl) {
    elements.downloadExampleLink.href = config.importExampleCsvAssetUrl;
  }
  elements.importButton.addEventListener("click", function () {
    void importUsers();
  });

  void loadUsers();
})();
