(function () {
  const config = window.DION_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    machineState: document.getElementById("machine-state"),
    statusMessage: document.getElementById("status-message"),
    idleReturnChip: document.getElementById("idle-return-chip"),
    dispenseTarget: document.getElementById("dispense-target"),
    inventoryQuantity: document.getElementById("inventory-quantity"),
    optionCountPill: document.getElementById("option-count-pill"),
    optionsEmptyState: document.getElementById("options-empty-state"),
    dispenseOptions: document.getElementById("dispense-options"),
    startAuthButton: document.getElementById("start-auth-button"),
    resetButton: document.getElementById("reset-button"),
    userCard: document.getElementById("user-card"),
    userStatePill: document.getElementById("user-state-pill"),
    userPlaceholder: document.querySelector(".user-placeholder"),
    userDetails: document.getElementById("user-details"),
    userName: document.getElementById("user-name"),
    userCode: document.getElementById("user-code"),
    userId: document.getElementById("user-id"),
    userRole: document.getElementById("user-role"),
    rfidUid: document.getElementById("rfid-uid"),
    dispenseButton: document.getElementById("dispense-button"),
    resultPanel: document.getElementById("result-panel"),
    resultStatePill: document.getElementById("result-state-pill"),
    resultTitle: document.getElementById("result-title"),
    resultDetail: document.getElementById("result-detail"),
    operationState: document.getElementById("operation-state"),
    confirmedQty: document.getElementById("confirmed-qty"),
    errorCode: document.getElementById("error-code"),
  };

  const state = {
    currentUser: null,
    currentRfidUid: null,
    selectedOption: null,
    availableOptions: [],
    isBusy: false,
    autoResetTimerId: null,
    countdownTimerId: null,
    autoResetDeadline: null,
  };

  const terminalResetDelayMs = config.autoResetTimeoutMs || 15000;

  function setBusy(isBusy) {
    state.isBusy = isBusy;
    elements.startAuthButton.disabled = isBusy;
    elements.resetButton.disabled = isBusy;
    syncDispenseButton();
  }

  function syncDispenseButton() {
    elements.dispenseButton.disabled = state.isBusy || !state.currentUser || !state.selectedOption;
  }

  function updateStatusTone(tone) {
    elements.statusPanel.className = "status-panel";
    elements.statusPanel.classList.add("status-" + tone);
  }

  function setMachineState(title, message, tone) {
    elements.machineState.textContent = title;
    elements.statusMessage.textContent = message;
    updateStatusTone(tone || "neutral");
  }

  function stopAutoReset() {
    if (state.autoResetTimerId) {
      window.clearTimeout(state.autoResetTimerId);
      state.autoResetTimerId = null;
    }
    if (state.countdownTimerId) {
      window.clearInterval(state.countdownTimerId);
      state.countdownTimerId = null;
    }
    state.autoResetDeadline = null;
    elements.idleReturnChip.classList.add("hidden");
    elements.idleReturnChip.textContent = "Скоро сброс";
  }

  function renderCountdown() {
    if (!state.autoResetDeadline) {
      return;
    }

    const remainingMs = Math.max(0, state.autoResetDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    elements.idleReturnChip.textContent = "Сброс через " + remainingSeconds + " с";
  }

  function scheduleAutoReset(reason) {
    stopAutoReset();
    state.autoResetDeadline = Date.now() + terminalResetDelayMs;
    elements.idleReturnChip.classList.remove("hidden");
    renderCountdown();
    state.countdownTimerId = window.setInterval(renderCountdown, 250);
    state.autoResetTimerId = window.setTimeout(function () {
      resetToIdle();
      if (reason) {
        setMachineState("Ожидание", "Готово для следующего пользователя. " + reason, "neutral");
      }
    }, terminalResetDelayMs);
  }

  function setResult(kind, title, detail, operation) {
    elements.resultPanel.className = "result-panel";
    if (kind === "success") {
      elements.resultPanel.classList.add("result-success");
      elements.resultStatePill.textContent = "Успех";
    } else if (kind === "warning") {
      elements.resultPanel.classList.add("result-warning");
      elements.resultStatePill.textContent = "Восстановление";
    } else if (kind === "failure") {
      elements.resultPanel.classList.add("result-failure");
      elements.resultStatePill.textContent = "Внимание";
    } else {
      elements.resultPanel.classList.add("result-neutral");
      elements.resultStatePill.textContent = "Ожидание";
    }

    elements.resultTitle.textContent = title;
    elements.resultDetail.textContent = detail;
    elements.operationState.textContent = operation && operation.operation_state ? operation.operation_state : "n/a";
    elements.confirmedQty.textContent =
      operation && operation.qty_confirmed !== null && operation.qty_confirmed !== undefined
        ? String(operation.qty_confirmed)
        : "n/a";
    elements.errorCode.textContent = operation && operation.error_code ? operation.error_code : "n/a";
  }

  function clearUser() {
    state.currentUser = null;
    state.currentRfidUid = null;
    elements.userCard.classList.add("user-card-empty");
    elements.userStatePill.textContent = "Ожидание";
    elements.userPlaceholder.classList.remove("hidden");
    elements.userDetails.classList.add("hidden");
    elements.userName.textContent = "";
    elements.userCode.textContent = "";
    elements.userId.textContent = "";
    elements.userRole.textContent = "";
    elements.rfidUid.textContent = "";
    syncDispenseButton();
  }

  function showUser(payload) {
    state.currentUser = payload.user;
    state.currentRfidUid = payload.rfid_uid;
    elements.userCard.classList.remove("user-card-empty");
    elements.userStatePill.textContent = "Готово";
    elements.userPlaceholder.classList.add("hidden");
    elements.userDetails.classList.remove("hidden");
    elements.userName.textContent = payload.user.full_name;
    elements.userCode.textContent = payload.user.user_code;
    elements.userId.textContent = String(payload.user.user_id);
    elements.userRole.textContent = payload.user.role_code || "n/a";
    elements.rfidUid.textContent = payload.rfid_uid;
    syncDispenseButton();
  }

  function resetToIdle() {
    stopAutoReset();
    clearUser();
    setBusy(false);
    setMachineState("Ожидание", "Готово для следующего пользователя. Приложите карту и нажмите старт.", "neutral");
    setResult("neutral", "Операций пока не было.", "Здесь появится результат последней выдачи.");
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

  function describeOption(option) {
    return (
      option.item_name +
      " | кол-во " +
      option.quantity +
      " | P" +
      String(option.drum_position).padStart(2, "0") +
      " Я" +
      String(option.lock_number).padStart(2, "0")
    );
  }

  function renderSelectedOption() {
    if (!state.selectedOption) {
      elements.dispenseTarget.textContent = "Выберите товар";
      syncDispenseButton();
      return;
    }

    elements.dispenseTarget.textContent = describeOption(state.selectedOption);
    syncDispenseButton();
  }

  function selectOption(optionKey) {
    state.selectedOption = null;
    for (let index = 0; index < state.availableOptions.length; index += 1) {
      const option = state.availableOptions[index];
      const currentKey = String(option.slot_id) + ":" + String(option.item_id);
      if (currentKey === optionKey) {
        state.selectedOption = option;
        break;
      }
    }

    if (!state.selectedOption && state.availableOptions.length) {
      state.selectedOption = state.availableOptions[0];
      optionKey = String(state.selectedOption.slot_id) + ":" + String(state.selectedOption.item_id);
    }

    const buttons = elements.dispenseOptions.querySelectorAll(".option-button");
    buttons.forEach(function (button) {
      button.classList.toggle("option-selected", button.dataset.optionKey === optionKey);
    });
    renderSelectedOption();
  }

  function renderOptions(options) {
    state.availableOptions = Array.isArray(options) ? options : [];
    const selectedKey = state.selectedOption
      ? String(state.selectedOption.slot_id) + ":" + String(state.selectedOption.item_id)
      : null;

    elements.dispenseOptions.innerHTML = "";
    elements.inventoryQuantity.textContent = String(state.availableOptions.length);
    elements.optionCountPill.textContent = String(state.availableOptions.length) + " доступно";

    if (!state.availableOptions.length) {
      state.selectedOption = null;
      elements.optionsEmptyState.textContent = "Нет доступных активных товаров в наличии.";
      elements.optionsEmptyState.classList.remove("hidden");
      renderSelectedOption();
      return;
    }

    elements.optionsEmptyState.classList.add("hidden");
    let nextSelectionKey = selectedKey;
    if (!nextSelectionKey) {
      nextSelectionKey = String(state.availableOptions[0].slot_id) + ":" + String(state.availableOptions[0].item_id);
    }

    state.availableOptions.forEach(function (option) {
      const button = document.createElement("button");
      const optionKey = String(option.slot_id) + ":" + String(option.item_id);
      button.type = "button";
      button.className = "option-button";
      button.dataset.optionKey = optionKey;
      button.innerHTML =
        '<span class="option-title">' +
        option.item_name +
        "</span>" +
        '<span class="option-meta">Артикул ' +
        option.item_sku +
        " | кол-во " +
        option.quantity +
        "</span>" +
        '<span class="option-meta">Позиция ' +
        option.drum_position +
        " | замок " +
        option.lock_number +
        "</span>";
      button.addEventListener("click", function () {
        selectOption(optionKey);
      });
      elements.dispenseOptions.appendChild(button);
    });

    selectOption(nextSelectionKey);
  }

  async function refreshOptions() {
    try {
      const { response, payload } = await readJson(config.optionsEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "Эндпоинт вариантов вернул ошибку.");
      }
      renderOptions(payload.options || []);
    } catch (error) {
      state.availableOptions = [];
      state.selectedOption = null;
      elements.inventoryQuantity.textContent = "Недоступно";
      elements.optionCountPill.textContent = "Недоступно";
      elements.optionsEmptyState.textContent = "Не удалось загрузить доступные остатки.";
      elements.optionsEmptyState.classList.remove("hidden");
      elements.dispenseOptions.innerHTML = "";
      renderSelectedOption();
      setResult("failure", "Ошибка загрузки остатков", String(error));
    }
  }

  async function startAuth() {
    stopAutoReset();
    clearUser();
    setBusy(true);
    setMachineState("Авторизация", "Приложите RFID-карту, чтобы начать.", "neutral");
    setResult("neutral", "Идет авторизация", "Ожидание чтения карты.");

    try {
      const { response, payload } = await readJson(config.authEndpoint, {
        method: "POST",
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const detail = payload.detail || "RFID-карта не принята.";
        setMachineState("Авторизация не выполнена", detail, "danger");
        setResult("failure", "Ошибка авторизации", detail);
        scheduleAutoReset("Экран сброшен после неуспешной авторизации.");
        return;
      }

      showUser(payload);
      setMachineState("Пользователь подтвержден", "Пользователь проверен. Выберите товар и выполните выдачу.", "success");
      setResult("success", "Пользователь авторизован", payload.user.full_name + " готов к выдаче.");
    } catch (error) {
      setMachineState("Ошибка авторизации", "UI не смог обратиться к backend-маршруту авторизации.", "danger");
      setResult("failure", "Ошибка авторизации", String(error));
      scheduleAutoReset("Экран сброшен после ошибки авторизации.");
    } finally {
      setBusy(false);
    }
  }

  function classifyOperation(operation) {
    if (!operation || !operation.operation_state) {
      return {
        kind: "failure",
        title: "Некорректный результат операции",
        detail: "Backend не вернул состояние операции.",
      };
    }

    if (operation.operation_state === "completed") {
      return {
        kind: "success",
        title: "Выдача завершена",
        detail: "Остатки обновлены, операция завершена успешно.",
      };
    }

    if (operation.operation_state === "recovery_required") {
      return {
        kind: "warning",
        title: "Требуется восстановление",
        detail: operation.error_message || "Для дальнейшей работы требуется восстановление.",
      };
    }

    return {
      kind: "failure",
      title: "Выдача не выполнена",
      detail: operation.error_message || operation.result || "Операция завершилась с ошибкой.",
    };
  }

  async function startDispense() {
    if (!state.currentUser || !state.selectedOption) {
      return;
    }

    stopAutoReset();
    setBusy(true);
    setMachineState("Выдача", "Идет выдача. Не приближайтесь к автомату.", "neutral");
    setResult("neutral", "Идет выдача", "Ожидание подтверждения от оборудования.");

    try {
      const requestPayload = {
        user_id: state.currentUser.user_id,
        item_id: state.selectedOption.item_id,
        slot_id: state.selectedOption.slot_id,
        quantity: config.dispenseQuantity || 1,
      };

      const { response, payload } = await readJson(config.dispenseEndpoint, {
        method: "POST",
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        const detail = payload.detail || "Backend отклонил запрос.";
        setMachineState("Ошибка выдачи", detail, "danger");
        setResult("failure", "Запрос на выдачу не выполнен", detail);
        scheduleAutoReset("Экран сброшен после неуспешного запроса на выдачу.");
        return;
      }

      const result = classifyOperation(payload);
      const tone = result.kind === "success" ? "success" : result.kind === "warning" ? "warning" : "danger";
      setMachineState("Результат", result.detail, tone);
      setResult(result.kind, result.title, result.detail, payload);
      await refreshOptions();
      scheduleAutoReset("Готово для следующего пользователя.");
    } catch (error) {
      setMachineState("Ошибка выдачи", "UI не смог обратиться к backend-маршруту выдачи.", "danger");
      setResult("failure", "Ошибка выдачи", String(error));
      scheduleAutoReset("Экран сброшен после ошибки выдачи.");
    } finally {
      setBusy(false);
    }
  }

  elements.startAuthButton.addEventListener("click", startAuth);
  elements.dispenseButton.addEventListener("click", startDispense);
  elements.resetButton.addEventListener("click", resetToIdle);

  resetToIdle();
  refreshOptions();
})();
