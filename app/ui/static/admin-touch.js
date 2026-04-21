(function () {
  const config = window.DION_ADMIN_TOUCH_UI_CONFIG || {};
  const UI_IDLE_TIMEOUT_MS = config.uiIdleTimeoutMs || 30000;
  const PRESENCE_COUNTDOWN_SECONDS = config.presenceCountdownSeconds || 30;
  const START_SCREEN_ROUTE = config.startScreenRoute || "/ui/user";
  const root = document.querySelector("[data-flow-root]");
  const presenceOverlay = document.getElementById("admin-touch-presence-overlay");
  const presenceOverlayCountdown = document.getElementById("admin-touch-presence-overlay-countdown");
  const presenceOverlayYesButton = document.getElementById("admin-touch-presence-overlay-yes");
  const presenceOverlayNoButton = document.getElementById("admin-touch-presence-overlay-no");

  if (
    !root ||
    !presenceOverlay ||
    !presenceOverlayCountdown ||
    !presenceOverlayYesButton ||
    !presenceOverlayNoButton
  ) {
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
  const importUsersState = {
    nextCheckResult: "confirm",
  };

  let inactivityTimerId = null;
  let presenceCountdownIntervalId = null;
  let presenceCountdownTimeoutId = null;
  let presenceCountdownDeadline = null;
  let presenceReturnView = null;
  let isPresenceOverlayVisible = false;
  let currentView = "landing";

  function clearTimers() {
    timers.forEach((timerId) => window.clearTimeout(timerId));
    timers.clear();
  }

  function clearInactivityTimer() {
    if (inactivityTimerId !== null) {
      window.clearTimeout(inactivityTimerId);
      inactivityTimerId = null;
    }
  }

  function clearPresenceCountdown() {
    if (presenceCountdownIntervalId !== null) {
      window.clearInterval(presenceCountdownIntervalId);
      presenceCountdownIntervalId = null;
    }

    if (presenceCountdownTimeoutId !== null) {
      window.clearTimeout(presenceCountdownTimeoutId);
      presenceCountdownTimeoutId = null;
    }

    presenceCountdownDeadline = null;
    presenceOverlayCountdown.textContent = String(PRESENCE_COUNTDOWN_SECONDS);
  }

  function setView(viewName) {
    views.forEach((node, key) => {
      const isActive = key === viewName;
      node.hidden = !isActive;
      node.classList.toggle("admin-touch-view-active", isActive);
    });
    currentView = viewName;
  }

  function schedule(callback, delayMs) {
    const timerId = window.setTimeout(() => {
      timers.delete(timerId);
      callback();
    }, delayMs);
    timers.add(timerId);
  }

  function canUseSharedInactivityTimeout(viewName) {
    return (
      viewName === "landing" ||
      viewName === "export-balances-confirm" ||
      viewName === "export-operations-period" ||
      viewName === "export-operations-confirm" ||
      viewName === "export-users-confirm" ||
      viewName === "import-users-precheck" ||
      viewName === "import-users-confirm" ||
      viewName === "import-users-error"
    );
  }

  function renderPresenceCountdown() {
    if (presenceCountdownDeadline === null) {
      return;
    }

    const remainingMs = Math.max(0, presenceCountdownDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    presenceOverlayCountdown.textContent = String(remainingSeconds);
  }

  function goToStartScreen() {
    window.location.assign(START_SCREEN_ROUTE);
  }

  function scheduleInactivityTimeout() {
    clearInactivityTimer();

    if (isPresenceOverlayVisible || !canUseSharedInactivityTimeout(currentView)) {
      return;
    }

    inactivityTimerId = window.setTimeout(() => {
      showPresenceOverlay();
    }, UI_IDLE_TIMEOUT_MS);
  }

  function hidePresenceOverlay(options) {
    const settings = options || {};

    clearPresenceCountdown();
    isPresenceOverlayVisible = false;
    presenceReturnView = null;
    presenceOverlay.hidden = true;
    presenceOverlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("admin-touch-presence-overlay-active");

    if (settings.restartIdleTimer !== false) {
      scheduleInactivityTimeout();
    }
  }

  function showPresenceOverlay() {
    if (isPresenceOverlayVisible || !canUseSharedInactivityTimeout(currentView)) {
      return;
    }

    clearInactivityTimer();
    clearPresenceCountdown();
    presenceReturnView = currentView;
    isPresenceOverlayVisible = true;
    presenceOverlay.hidden = false;
    presenceOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("admin-touch-presence-overlay-active");
    presenceCountdownDeadline = Date.now() + (PRESENCE_COUNTDOWN_SECONDS * 1000);
    renderPresenceCountdown();
    presenceCountdownIntervalId = window.setInterval(renderPresenceCountdown, 250);
    presenceCountdownTimeoutId = window.setTimeout(() => {
      goToStartScreen();
    }, PRESENCE_COUNTDOWN_SECONDS * 1000);
    presenceOverlayYesButton.focus();
  }

  function handlePresenceResume() {
    if (!isPresenceOverlayVisible) {
      return;
    }

    if (presenceReturnView) {
      setView(presenceReturnView);
    }

    hidePresenceOverlay({ restartIdleTimer: true });
  }

  function handlePresenceInteraction(event) {
    const target = event.target;

    if (!(target instanceof Element)) {
      return;
    }

    if (target.closest("#admin-touch-presence-overlay")) {
      return;
    }

    if (isPresenceOverlayVisible || !canUseSharedInactivityTimeout(currentView)) {
      return;
    }

    scheduleInactivityTimeout();
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
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("landing");
    scheduleInactivityTimeout();
  }

  function showUsersConfirmation() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("export-users-confirm");
    scheduleInactivityTimeout();
  }

  function showImportUsersPrecheck() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("import-users-precheck");
    scheduleInactivityTimeout();
  }

  function showImportUsersConfirmation() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("import-users-confirm");
    scheduleInactivityTimeout();
  }

  function showImportUsersError() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("import-users-error");
    scheduleInactivityTimeout();
  }

  function showBalancesConfirmation() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    setView("export-balances-confirm");
    scheduleInactivityTimeout();
  }

  function showOperationsPeriodSelection() {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    syncOperationsPeriodUi();
    setView("export-operations-period");
    scheduleInactivityTimeout();
  }

  function showOperationsConfirmation() {
    if (!hasCompleteOperationsPeriod()) {
      showOperationsPeriodSelection();
      return;
    }

    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    syncOperationsPeriodUi();
    setView("export-operations-confirm");
    scheduleInactivityTimeout();
  }

  function startTimedFlow(progressViewName, successViewName) {
    clearTimers();
    hidePresenceOverlay({ restartIdleTimer: false });
    clearInactivityTimer();
    setView(progressViewName);
    schedule(() => {
      setView(successViewName);
      schedule(showLanding, config.successReturnDelayMs || 2400);
    }, config.progressAdvanceDelayMs || 1800);
  }

  function startExportUsersFlow() {
    startTimedFlow("export-users-progress", "export-users-success");
  }

  function runImportUsersCheck() {
    const shouldConfirm = importUsersState.nextCheckResult === "confirm";
    importUsersState.nextCheckResult = shouldConfirm ? "error" : "confirm";

    if (shouldConfirm) {
      showImportUsersConfirmation();
      return;
    }

    showImportUsersError();
  }

  function startImportUsersFlow() {
    startTimedFlow("import-users-progress", "import-users-success");
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

    if (action === "import-users") {
      showImportUsersPrecheck();
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

    if (action === "exit-admin-touch") {
      goToStartScreen();
      return;
    }

    if (action === "back-to-landing") {
      showLanding();
      return;
    }

    if (action === "retry-import-users") {
      showImportUsersPrecheck();
      return;
    }

    if (action === "check-import-users") {
      runImportUsersCheck();
      return;
    }

    if (action === "continue-export-operations") {
      showOperationsConfirmation();
      return;
    }

    if (action === "start-import-users") {
      startImportUsersFlow();
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

  presenceOverlayYesButton.addEventListener("click", handlePresenceResume);
  presenceOverlayNoButton.addEventListener("click", goToStartScreen);

  document.addEventListener("pointerdown", handlePresenceInteraction, true);
  document.addEventListener(
    "keydown",
    (event) => {
      if (isPresenceOverlayVisible) {
        return;
      }

      handlePresenceInteraction(event);
    },
    true,
  );
  document.addEventListener("touchstart", handlePresenceInteraction, true);

  window.addEventListener("beforeunload", () => {
    clearTimers();
    clearInactivityTimer();
    clearPresenceCountdown();
  });

  syncOperationsPeriodUi();
  showLanding();
})();
