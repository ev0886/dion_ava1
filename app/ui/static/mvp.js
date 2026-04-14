(function () {
  const config = window.DION_UI_CONFIG;

  const elements = {
    statusPanel: document.getElementById("status-panel"),
    machineState: document.getElementById("machine-state"),
    statusMessage: document.getElementById("status-message"),
    idleReturnChip: document.getElementById("idle-return-chip"),
    dispenseTarget: document.getElementById("dispense-target"),
    inventoryQuantity: document.getElementById("inventory-quantity"),
    usbStatusTitle: document.getElementById("usb-status-title"),
    usbStatusDetail: document.getElementById("usb-status-detail"),
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
    elements.idleReturnChip.textContent = "Soon reset";
  }

  function renderCountdown() {
    if (!state.autoResetDeadline) {
      return;
    }

    const remainingMs = Math.max(0, state.autoResetDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    elements.idleReturnChip.textContent = "Reset in " + remainingSeconds + " s";
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
        setMachineState("Ready", "Ready for the next user. " + reason, "neutral");
      }
    }, terminalResetDelayMs);
  }

  function setResult(kind, title, detail, operation) {
    elements.resultPanel.className = "result-panel";
    if (kind === "success") {
      elements.resultPanel.classList.add("result-success");
      elements.resultStatePill.textContent = "Success";
    } else if (kind === "warning") {
      elements.resultPanel.classList.add("result-warning");
      elements.resultStatePill.textContent = "Recovery";
    } else if (kind === "failure") {
      elements.resultPanel.classList.add("result-failure");
      elements.resultStatePill.textContent = "Attention";
    } else {
      elements.resultPanel.classList.add("result-neutral");
      elements.resultStatePill.textContent = "Idle";
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
    elements.userStatePill.textContent = "Idle";
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
    elements.userStatePill.textContent = "Ready";
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
    setMachineState("Idle", "Ready for the next user. Tap start and present a card.", "neutral");
    setResult("neutral", "No operations yet.", "The latest dispense result will appear here.");
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
    return option.item_name + " | qty " + option.total_quantity;
  }

  function renderUsbStatus(payload) {
    if (!elements.usbStatusTitle || !elements.usbStatusDetail) {
      return;
    }

    if (payload && payload.usb_available) {
      elements.usbStatusTitle.textContent = "\u0055\u0053\u0042-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d";
      elements.usbStatusDetail.textContent = payload.mount_path
        ? "\u041f\u0443\u0442\u044c: " + payload.mount_path
        : "\u0422\u043e\u0447\u043a\u0430 \u043c\u043e\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u0430.";
      return;
    }

    elements.usbStatusTitle.textContent = "\u0055\u0053\u0042-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d";
    elements.usbStatusDetail.textContent =
      "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u0435 USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043a Raspberry Pi \u0438 \u0434\u043e\u0436\u0434\u0438\u0442\u0435\u0441\u044c \u0435\u0433\u043e \u043c\u043e\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f.";
  }

  async function refreshUsbStatus() {
    if (!config.usbStatusEndpoint) {
      return;
    }

    try {
      const { response, payload } = await readJson(config.usbStatusEndpoint, { method: "GET" });
      if (!response.ok) {
        throw new Error(payload.detail || "USB status endpoint returned an error.");
      }
      renderUsbStatus(payload);
    } catch (error) {
      elements.usbStatusTitle.textContent = "\u0055\u0053\u0042-\u0441\u0442\u0430\u0442\u0443\u0441 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d";
      elements.usbStatusDetail.textContent =
        "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0441\u0442\u0430\u0442\u0443\u0441 USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044f.";
    }
  }

  function renderSelectedOption() {
    if (!state.selectedOption) {
      elements.dispenseTarget.textContent = "Select an item";
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
      const currentKey = String(option.item_id);
      if (currentKey === optionKey) {
        state.selectedOption = option;
        break;
      }
    }

    if (!state.selectedOption && state.availableOptions.length) {
      state.selectedOption = state.availableOptions[0];
      optionKey = String(state.selectedOption.item_id);
    }

    const buttons = elements.dispenseOptions.querySelectorAll(".option-button");
    buttons.forEach(function (button) {
      button.classList.toggle("option-selected", button.dataset.optionKey === optionKey);
    });
    renderSelectedOption();
  }

  function renderOptions(options) {
    state.availableOptions = Array.isArray(options) ? options : [];
    const selectedKey = state.selectedOption ? String(state.selectedOption.item_id) : null;

    elements.dispenseOptions.innerHTML = "";
    const totalQuantity = state.availableOptions.reduce(function (sum, option) {
      return sum + (option.total_quantity || 0);
    }, 0);
    elements.inventoryQuantity.textContent = String(totalQuantity);
    elements.optionCountPill.textContent = String(state.availableOptions.length) + " available";

    if (!state.availableOptions.length) {
      state.selectedOption = null;
      elements.optionsEmptyState.textContent = "No stocked items available.";
      elements.optionsEmptyState.classList.remove("hidden");
      renderSelectedOption();
      return;
    }

    elements.optionsEmptyState.classList.add("hidden");
    let nextSelectionKey = selectedKey;
    if (!nextSelectionKey) {
      nextSelectionKey = String(state.availableOptions[0].item_id);
    }

    state.availableOptions.forEach(function (option) {
      const button = document.createElement("button");
      const optionKey = String(option.item_id);
      button.type = "button";
      button.className = "option-button";
      button.dataset.optionKey = optionKey;
      button.innerHTML =
        '<span class="option-title">' +
        option.item_name +
        "</span>" +
        '<span class="option-meta">Qty ' +
        option.total_quantity +
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
        throw new Error(payload.detail || "Options endpoint returned an error.");
      }
      renderOptions(payload.options || []);
    } catch (error) {
      state.availableOptions = [];
      state.selectedOption = null;
      elements.inventoryQuantity.textContent = "Unavailable";
      elements.optionCountPill.textContent = "Unavailable";
      elements.optionsEmptyState.textContent = "Could not load stocked items.";
      elements.optionsEmptyState.classList.remove("hidden");
      elements.dispenseOptions.innerHTML = "";
      renderSelectedOption();
      setResult("failure", "Inventory load failed", String(error));
    }
  }

  async function startAuth() {
    stopAutoReset();
    clearUser();
    setBusy(true);
    setMachineState("Authorization", "Present an RFID card to continue.", "neutral");
    setResult("neutral", "Authorizing", "Waiting for card read.");

    try {
      const { response, payload } = await readJson(config.authEndpoint, {
        method: "POST",
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const detail = payload.detail || "RFID card was not accepted.";
        setMachineState("Authorization failed", detail, "danger");
        setResult("failure", "Authorization failed", detail);
        scheduleAutoReset("Screen reset after failed authorization.");
        return;
      }

      showUser(payload);
      setMachineState("User confirmed", "Select an item and start dispense.", "success");
      setResult("success", "User authorized", payload.user.full_name + " is ready for dispense.");
    } catch (error) {
      setMachineState("Authorization error", "UI could not reach the backend auth route.", "danger");
      setResult("failure", "Authorization error", String(error));
      scheduleAutoReset("Screen reset after authorization error.");
    } finally {
      setBusy(false);
    }
  }

  function classifyOperation(operation) {
    if (!operation || !operation.operation_state) {
      return {
        kind: "failure",
        title: "Invalid operation result",
        detail: "Backend did not return an operation state.",
      };
    }

    if (operation.operation_state === "completed") {
      return {
        kind: "success",
        title: "Dispense complete",
        detail: "Inventory was updated and dispense completed successfully.",
      };
    }

    if (operation.operation_state === "recovery_required") {
      return {
        kind: "warning",
        title: "Recovery required",
        detail: operation.error_message || "Recovery is required before further work.",
      };
    }

    return {
      kind: "failure",
      title: "Dispense failed",
      detail: operation.error_message || operation.result || "Operation finished with an error.",
    };
  }

  async function startDispense() {
    if (!state.currentUser || !state.selectedOption) {
      return;
    }

    stopAutoReset();
    setBusy(true);
    setMachineState("Dispense", "Dispense in progress. Do not approach the machine.", "neutral");
    setResult("neutral", "Dispense in progress", "Waiting for hardware confirmation.");

    try {
      const requestPayload = {
        user_id: state.currentUser.user_id,
        item_id: state.selectedOption.item_id,
        quantity: config.dispenseQuantity || 1,
      };

      const { response, payload } = await readJson(config.dispenseEndpoint, {
        method: "POST",
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        const detail = payload.detail || "Backend rejected the request.";
        setMachineState("Dispense error", detail, "danger");
        setResult("failure", "Dispense request failed", detail);
        scheduleAutoReset("Screen reset after failed dispense request.");
        return;
      }

      const result = classifyOperation(payload);
      const tone = result.kind === "success" ? "success" : result.kind === "warning" ? "warning" : "danger";
      setMachineState("Result", result.detail, tone);
      setResult(result.kind, result.title, result.detail, payload);
      await refreshOptions();
      scheduleAutoReset("Ready for the next user.");
    } catch (error) {
      setMachineState("Dispense error", "UI could not reach the backend dispense route.", "danger");
      setResult("failure", "Dispense error", String(error));
      scheduleAutoReset("Screen reset after dispense error.");
    } finally {
      setBusy(false);
    }
  }

  elements.startAuthButton.addEventListener("click", startAuth);
  elements.dispenseButton.addEventListener("click", startDispense);
  elements.resetButton.addEventListener("click", resetToIdle);

  resetToIdle();
  refreshUsbStatus();
  refreshOptions();
})();
