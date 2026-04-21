(function () {
  const config = window.DION_ADMIN_TOUCH_UI_CONFIG || {};
  const root = document.querySelector("[data-flow-root]");

  if (!root) {
    return;
  }

  const views = new Map(
    Array.from(root.querySelectorAll("[data-view]")).map((node) => [node.dataset.view, node]),
  );
  const timers = new Set();
  const operationsFields = {
    from: root.querySelector('[data-period-field="from"]'),
    to: root.querySelector('[data-period-field="to"]'),
  };
  const operationsNextButton = root.querySelector('[data-role="operations-next"]');
  const operationsPeriodSummaries = Array.from(
    root.querySelectorAll('[data-role="operations-period-summary"]'),
  );
  const operationsPeriodState = {
    from: config.operationsDefaultDateFrom || "01.04.2026",
    to: config.operationsDefaultDateTo || "21.04.2026",
  };

  function clearTimers() {
    timers.forEach((timerId) => window.clearTimeout(timerId));
    timers.clear();
  }

  function setView(viewName) {
    views.forEach((node, key) => {
      const isActive = key === viewName;
      node.hidden = !isActive;
      node.classList.toggle("admin-touch-view-active", isActive);
    });
  }

  function schedule(callback, delayMs) {
    const timerId = window.setTimeout(() => {
      timers.delete(timerId);
      callback();
    }, delayMs);
    timers.add(timerId);
  }

  function hasCompleteOperationsPeriod() {
    return Boolean(operationsPeriodState.from.trim() && operationsPeriodState.to.trim());
  }

  function getOperationsPeriodLabel() {
    return `Период: ${operationsPeriodState.from} - ${operationsPeriodState.to}`;
  }

  function syncOperationsPeriodUi() {
    if (operationsFields.from) {
      operationsFields.from.value = operationsPeriodState.from;
    }

    if (operationsFields.to) {
      operationsFields.to.value = operationsPeriodState.to;
    }

    if (operationsNextButton) {
      operationsNextButton.disabled = !hasCompleteOperationsPeriod();
    }

    const summaryText = getOperationsPeriodLabel();
    operationsPeriodSummaries.forEach((node) => {
      node.textContent = summaryText;
    });
  }

  function showLanding() {
    clearTimers();
    setView("landing");
  }

  function showUsersConfirmation() {
    clearTimers();
    setView("export-users-confirm");
  }

  function showBalancesConfirmation() {
    clearTimers();
    setView("export-balances-confirm");
  }

  function showOperationsPeriodSelection() {
    clearTimers();
    syncOperationsPeriodUi();
    setView("export-operations-period");
  }

  function showOperationsConfirmation() {
    if (!hasCompleteOperationsPeriod()) {
      showOperationsPeriodSelection();
      return;
    }

    clearTimers();
    syncOperationsPeriodUi();
    setView("export-operations-confirm");
  }

  function startTimedFlow(progressViewName, successViewName) {
    clearTimers();
    setView(progressViewName);
    schedule(() => {
      setView(successViewName);
      schedule(showLanding, config.successReturnDelayMs || 2400);
    }, config.progressAdvanceDelayMs || 1800);
  }

  function startExportUsersFlow() {
    startTimedFlow("export-users-progress", "export-users-success");
  }

  function startExportBalancesFlow() {
    startTimedFlow("export-balances-progress", "export-balances-success");
  }

  function startExportOperationsFlow() {
    syncOperationsPeriodUi();
    startTimedFlow("export-operations-progress", "export-operations-success");
  }

  root.addEventListener("input", (event) => {
    const field = event.target.closest("[data-period-field]");

    if (!field) {
      return;
    }

    const key = field.dataset.periodField;
    operationsPeriodState[key] = field.value.trim();
    syncOperationsPeriodUi();
  });

  root.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");

    if (!target) {
      return;
    }

    const { action } = target.dataset;

    if (action === "export-balances") {
      showBalancesConfirmation();
      return;
    }

    if (action === "export-operations") {
      showOperationsPeriodSelection();
      return;
    }

    if (action === "export-users") {
      showUsersConfirmation();
      return;
    }

    if (action === "back-to-landing") {
      showLanding();
      return;
    }

    if (action === "continue-export-operations") {
      showOperationsConfirmation();
      return;
    }

    if (action === "start-export-users") {
      startExportUsersFlow();
      return;
    }

    if (action === "start-export-balances") {
      startExportBalancesFlow();
      return;
    }

    if (action === "start-export-operations") {
      startExportOperationsFlow();
    }
  });

  window.addEventListener("beforeunload", clearTimers);
  syncOperationsPeriodUi();
  showLanding();
})();
