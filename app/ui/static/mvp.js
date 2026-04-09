(function () {
  const config = window.DION_UI_CONFIG;

  const elements = {
    machineState: document.getElementById("machine-state"),
    statusMessage: document.getElementById("status-message"),
    dispenseTarget: document.getElementById("dispense-target"),
    inventoryQuantity: document.getElementById("inventory-quantity"),
    startAuthButton: document.getElementById("start-auth-button"),
    resetButton: document.getElementById("reset-button"),
    userCard: document.getElementById("user-card"),
    userPlaceholder: document.querySelector(".user-placeholder"),
    userDetails: document.getElementById("user-details"),
    userName: document.getElementById("user-name"),
    userCode: document.getElementById("user-code"),
    userId: document.getElementById("user-id"),
    userRole: document.getElementById("user-role"),
    rfidUid: document.getElementById("rfid-uid"),
    dispenseButton: document.getElementById("dispense-button"),
    resultPanel: document.getElementById("result-panel"),
    resultTitle: document.getElementById("result-title"),
    resultDetail: document.getElementById("result-detail"),
    operationState: document.getElementById("operation-state"),
    confirmedQty: document.getElementById("confirmed-qty"),
    errorCode: document.getElementById("error-code"),
  };

  const state = {
    currentUser: null,
    currentRfidUid: null,
    isBusy: false,
  };

  function setBusy(isBusy) {
    state.isBusy = isBusy;
    elements.startAuthButton.disabled = isBusy;
    elements.resetButton.disabled = isBusy;
    elements.dispenseButton.disabled = isBusy || !state.currentUser;
  }

  function setMachineState(title, message) {
    elements.machineState.textContent = title;
    elements.statusMessage.textContent = message;
  }

  function setResult(kind, title, detail, operation) {
    elements.resultPanel.className = "result-panel";
    if (kind === "success") {
      elements.resultPanel.classList.add("result-success");
    } else if (kind === "warning") {
      elements.resultPanel.classList.add("result-warning");
    } else if (kind === "failure") {
      elements.resultPanel.classList.add("result-failure");
    } else {
      elements.resultPanel.classList.add("result-neutral");
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
    elements.userPlaceholder.classList.remove("hidden");
    elements.userDetails.classList.add("hidden");
    elements.userName.textContent = "";
    elements.userCode.textContent = "";
    elements.userId.textContent = "";
    elements.userRole.textContent = "";
    elements.rfidUid.textContent = "";
    elements.dispenseButton.disabled = true;
  }

  function showUser(payload) {
    state.currentUser = payload.user;
    state.currentRfidUid = payload.rfid_uid;
    elements.userCard.classList.remove("user-card-empty");
    elements.userPlaceholder.classList.add("hidden");
    elements.userDetails.classList.remove("hidden");
    elements.userName.textContent = payload.user.full_name;
    elements.userCode.textContent = payload.user.user_code;
    elements.userId.textContent = String(payload.user.user_id);
    elements.userRole.textContent = payload.user.role_code || "n/a";
    elements.rfidUid.textContent = payload.rfid_uid;
    elements.dispenseButton.disabled = state.isBusy;
  }

  function resetToIdle() {
    clearUser();
    setBusy(false);
    setMachineState("Idle", "Ready for the next user. Present a card and start authorization.");
    setResult("neutral", "No operation yet.", "The result for the last dispense will appear here.");
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

  async function refreshInventory() {
    const { response, payload } = await readJson(config.inventoryEndpoint, { method: "GET" });
    if (!response.ok) {
      elements.inventoryQuantity.textContent = "Unavailable";
      return;
    }

    const quantity = payload.balance ? payload.balance.quantity : "Unknown";
    elements.inventoryQuantity.textContent = String(quantity);
  }

  async function startAuth() {
    clearUser();
    setBusy(true);
    setMachineState("Authorizing", "Waiting for RFID card on the real backend authorization endpoint.");
    setResult("neutral", "Authorization in progress", "Present card now.");

    try {
      const { response, payload } = await readJson(config.authEndpoint, {
        method: "POST",
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        setMachineState("Authorization Failed", payload.detail || "RFID authorization failed.");
        setResult("failure", "Authorization failed", payload.detail || "RFID card was not accepted.");
        return;
      }

      showUser(payload);
      setMachineState("Authenticated", "User resolved. Dispense is enabled for the configured smoke-path item.");
      setResult("success", "User authenticated", payload.user.full_name + " is ready to dispense.");
    } catch (error) {
      setMachineState("Authorization Error", "The UI could not reach the backend authorization path.");
      setResult("failure", "Authorization error", String(error));
    } finally {
      setBusy(false);
    }
  }

  function classifyOperation(operation) {
    if (!operation || !operation.operation_state) {
      return {
        kind: "failure",
        title: "Invalid operation result",
        detail: "No operation state returned from backend.",
      };
    }

    if (operation.operation_state === "completed") {
      return {
        kind: "success",
        title: "Dispense completed",
        detail: "Inventory write completed and the operation finished successfully.",
      };
    }

    if (operation.operation_state === "recovery_required") {
      return {
        kind: "warning",
        title: "Recovery required",
        detail: operation.error_message || "Operation requires recovery before further use.",
      };
    }

    return {
      kind: "failure",
      title: "Dispense failed",
      detail: operation.error_message || operation.result || "Operation did not complete successfully.",
    };
  }

  async function startDispense() {
    if (!state.currentUser) {
      return;
    }

    setBusy(true);
    setMachineState("Dispensing", "Real dispense is running through the backend operation endpoint.");
    setResult("neutral", "Dispense in progress", "Wait for the backend and hardware flow to finish.");

    try {
      const requestPayload = {
        user_id: state.currentUser.user_id,
        item_id: config.dispenseRequest.item_id,
        slot_id: config.dispenseRequest.slot_id,
        quantity: config.dispenseRequest.quantity,
      };

      const { response, payload } = await readJson(config.dispenseEndpoint, {
        method: "POST",
        body: JSON.stringify(requestPayload),
      });

      if (!response.ok) {
        setMachineState("Dispense Error", payload.detail || "Dispense request failed.");
        setResult("failure", "Dispense request failed", payload.detail || "Backend rejected the request.");
        return;
      }

      const result = classifyOperation(payload);
      setMachineState("Result", result.detail);
      setResult(result.kind, result.title, result.detail, payload);
      await refreshInventory();
    } catch (error) {
      setMachineState("Dispense Error", "The UI could not reach the backend dispense path.");
      setResult("failure", "Dispense error", String(error));
    } finally {
      setBusy(false);
    }
  }

  elements.startAuthButton.addEventListener("click", startAuth);
  elements.dispenseButton.addEventListener("click", startDispense);
  elements.resetButton.addEventListener("click", resetToIdle);

  elements.dispenseTarget.textContent =
    "slot " +
    config.dispenseRequest.slot_id +
    ", item " +
    config.dispenseRequest.item_id +
    ", qty " +
    config.dispenseRequest.quantity;

  resetToIdle();
  refreshInventory();
})();
