(function () {
  const config = window.DION_UI_CONFIG || {};
  const UI_IDLE_TIMEOUT_MS = 30000;
  const PRESENCE_COUNTDOWN_SECONDS = 30;
  const userDispenseWaitingDelayMs = 1800;
  const AUTH_READ_AND_RESOLVE_RFID_ENDPOINT = config.authReadAndResolveRfidEndpoint || "";
  const TOUCH_ROLE_ROUTES = config.touchRoleRoutes || {};
  const TOUCH_NOMENCLATURE_ENDPOINT = config.listTouchNomenclatureEndpoint || "";
  const EMPTY_NOMENCLATURE_MESSAGE =
    config.emptyNomenclatureMessage || "\u041d\u043e\u043c\u0435\u043d\u043a\u043b\u0430\u0442\u0443\u0440\u0430 \u043d\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u0430";
  const DEFAULT_AUTH_ERROR_TITLE = "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d";
  const INACTIVE_AUTH_ERROR_TITLE = "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435\u0430\u043a\u0442\u0438\u0432\u0435\u043d";
  const UNSUPPORTED_ROLE_AUTH_ERROR_TITLE =
    "\u0420\u043e\u043b\u044c \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442\u0441\u044f";

  const elements = {
    screenKicker: document.getElementById("screen-kicker"),
    screenTitle: document.getElementById("screen-title"),
    screenMessage: document.getElementById("screen-message"),
    screenBody: document.querySelector(".screen-body"),
    countdownPanel: document.getElementById("countdown-panel"),
    countdownValue: document.getElementById("countdown-value"),
    screenActions: document.getElementById("screen-actions"),
    screenCard: document.querySelector(".screen-card"),
    presenceOverlay: document.getElementById("presence-overlay"),
    presenceOverlayCountdown: document.getElementById("presence-overlay-countdown"),
    presenceOverlayYesButton: document.getElementById("presence-overlay-yes-button"),
    presenceOverlayNoButton: document.getElementById("presence-overlay-no-button"),
  };

  const state = {
    currentScreen: "start",
    previousScreen: null,
    idleTimeoutId: null,
    delayedTransitionId: null,
    countdownIntervalId: null,
    countdownTimeoutId: null,
    countdownDeadline: null,
    presencePreviousScreen: null,
    isPresenceOverlayVisible: false,
    selectedUserItemId: null,
    userListExpanded: false,
    userItems: [],
    authErrorTitle: DEFAULT_AUTH_ERROR_TITLE,
    authResolvedUser: null,
    pendingRoutePath: null,
    authRequestToken: 0,
  };

  const screens = {
    start: {
      title: "\u0413\u043e\u0442\u043e\u0432 \u043a \u0432\u044b\u0434\u0430\u0447\u0435",
      actions: [{ label: "\u041d\u0430\u0447\u0430\u0442\u044c", action: "go-auth", tone: "primary" }],
      enableIdleTimeout: true,
    },
    auth: {
      title: "\u041f\u0440\u0438\u043b\u043e\u0436\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u0443",
      actions: [{ label: "\u0412\u044b\u0439\u0442\u0438", action: "confirm-exit", tone: "ghost" }],
      enableIdleTimeout: true,
    },
    authError: {
      title: function () {
        return state.authErrorTitle || DEFAULT_AUTH_ERROR_TITLE;
      },
      autoReturnMs: config.authErrorReturnTimeoutMs,
      actions: [],
    },
    authSuccess: {
      title: "\u0423\u0441\u043f\u0435\u0448\u043d\u043e!",
      autoReturnMs: config.authSuccessRouteDelayMs,
      actions: [{ label: "\u041e\u0442\u043c\u0435\u043d\u0430", action: "go-start", tone: "ghost" }],
    },
    userItemSelect: {
      kicker: "\u0412\u044b\u0431\u043e\u0440 \u0442\u043e\u0432\u0430\u0440\u0430",
      title: "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0439 \u0442\u043e\u0432\u0430\u0440",
      message: "\u041e\u0442\u043c\u0435\u0442\u044c\u0442\u0435 \u043e\u0434\u043d\u0443 \u043f\u043e\u0437\u0438\u0446\u0438\u044e \u0434\u043b\u044f \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0435\u043d\u0438\u044f.",
      actions: [
        { label: "\u041e\u0442\u043c\u0435\u043d\u0430", action: "go-start", tone: "ghost" },
        { label: "\u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c", action: "go-user-item-next", tone: "primary", disabled: isUserItemSelectionEmpty },
      ],
      enableIdleTimeout: true,
      roleTheme: "user",
    },
    userItemAvailable: {
      kicker: "\u041f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e",
      title: "\u041e\u0436\u0438\u0434\u0430\u0439\u0442\u0435 \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u044f \u044f\u0447\u0435\u0439\u043a\u0438!",
      message: getAvailableUserItemMessage,
      autoReturnMs: userDispenseWaitingDelayMs,
      autoReturnTarget: "userItemSuccess",
      actions: [],
      enableIdleTimeout: true,
      roleTheme: "user",
    },
    userItemSuccess: {
      kicker: "\u0413\u043e\u0442\u043e\u0432\u043e",
      title: "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
      message: getUserItemSuccessMessage,
      actions: [{ label: "\u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", action: "go-start", tone: "primary" }],
      enableIdleTimeout: true,
      roleTheme: "user",
    },
    userItemUnavailable: {
      kicker: "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e",
      title:
        "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0432 \u0434\u0430\u043d\u043d\u044b\u0439 \u043c\u043e\u043c\u0435\u043d\u0442 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e",
      message: getUnavailableUserItemMessage,
      actions: [
        { label: "\u041a \u0442\u043e\u0432\u0430\u0440\u0430\u043c", action: "back-to-user-items", tone: "secondary" },
        { label: "\u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", action: "go-start", tone: "ghost" },
      ],
      enableIdleTimeout: true,
      roleTheme: "user",
    },
    exitPrompt: {
      title: "\u0412\u044b\u0439\u0442\u0438?",
      actions: [
        { label: "\u041d\u0435\u0442", action: "resume-previous", tone: "secondary" },
        { label: "\u0414\u0430", action: "go-start", tone: "primary" },
      ],
      enableIdleTimeout: true,
    },
  };

  function clearTimers() {
    if (state.idleTimeoutId) {
      window.clearTimeout(state.idleTimeoutId);
      state.idleTimeoutId = null;
    }
    if (state.delayedTransitionId) {
      window.clearTimeout(state.delayedTransitionId);
      state.delayedTransitionId = null;
    }
    if (state.countdownIntervalId) {
      window.clearInterval(state.countdownIntervalId);
      state.countdownIntervalId = null;
    }
    if (state.countdownTimeoutId) {
      window.clearTimeout(state.countdownTimeoutId);
      state.countdownTimeoutId = null;
    }
    state.countdownDeadline = null;
  }

  function canUseSharedInactivityTimeout(screenKey) {
    return (
      screenKey !== "start" &&
      screenKey !== "auth" &&
      screenKey !== "authError" &&
      screenKey !== "authSuccess" &&
      screenKey !== "userItemSuccess" &&
      screenKey !== "userItemUnavailable"
    );
  }

  function renderCountdown() {
    if (!state.countdownDeadline) {
      return;
    }

    const remainingMs = Math.max(0, state.countdownDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    const text = String(remainingSeconds);
    elements.countdownValue.textContent = text;

    if (state.isPresenceOverlayVisible) {
      elements.presenceOverlayCountdown.textContent = text;
    }
  }

  function stopCountdown() {
    elements.countdownPanel.classList.add("hidden");
    elements.countdownValue.textContent = "0";
    elements.presenceOverlayCountdown.textContent = String(PRESENCE_COUNTDOWN_SECONDS);
  }

  function startCountdown(durationSeconds, onExpire) {
    state.countdownDeadline = Date.now() + durationSeconds * 1000;
    if (!state.isPresenceOverlayVisible) {
      elements.countdownPanel.classList.remove("hidden");
    }
    renderCountdown();
    state.countdownIntervalId = window.setInterval(renderCountdown, 250);
    state.countdownTimeoutId = window.setTimeout(onExpire, durationSeconds * 1000);
  }

  function scheduleIdleTimeout() {
    if (state.isPresenceOverlayVisible || !canUseSharedInactivityTimeout(state.currentScreen)) {
      return;
    }

    state.idleTimeoutId = window.setTimeout(function () {
      showTimeoutPrompt();
    }, UI_IDLE_TIMEOUT_MS);
  }

  function maybeScheduleAutoTransition(screenKey) {
    const screen = screens[screenKey];
    if (!screen || !screen.autoReturnMs) {
      return;
    }

    state.delayedTransitionId = window.setTimeout(function () {
      if (typeof screen.autoReturnAction === "function") {
        screen.autoReturnAction();
        return;
      }
      showScreen(screen.autoReturnTarget || "start");
    }, screen.autoReturnMs);
  }

  function ensureScreenContent() {
    let screenContent = document.getElementById("screen-content");
    if (!screenContent) {
      screenContent = document.createElement("div");
      screenContent.id = "screen-content";
      screenContent.className = "screen-content hidden";
      elements.screenBody.insertBefore(screenContent, elements.countdownPanel);
    }
    return screenContent;
  }

  function isUserItemSelectionEmpty() {
    return !state.selectedUserItemId;
  }

  function getSelectedUserItem() {
    return state.userItems.find(function (item) {
      return item.id === state.selectedUserItemId;
    }) || null;
  }

  function hasUserItems() {
    return state.userItems.length > 0;
  }

  function getAvailableUserItemMessage() {
    const selectedItem = getSelectedUserItem();
    if (!selectedItem) {
      return "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u043e\u0432\u0430\u0440, \u0447\u0442\u043e\u0431\u044b \u043f\u0435\u0440\u0435\u0439\u0442\u0438 \u043a \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u043c\u0443 \u0448\u0430\u0433\u0443.";
    }
    return (
      "\u0414\u043b\u044f \u0442\u043e\u0432\u0430\u0440\u0430 \u00ab" +
      selectedItem.name +
      "\u00bb \u0441\u0435\u0439\u0447\u0430\u0441 \u043e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u044d\u043a\u0440\u0430\u043d \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f."
    );
  }

  function getUserItemSuccessMessage() {
    const selectedItem = getSelectedUserItem();
    if (!selectedItem) {
      return "\u0417\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u043e\u0432\u0430\u0440, \u0437\u0430\u043a\u0440\u043e\u0439\u0442\u0435 \u044f\u0447\u0435\u0439\u043a\u0443 \u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e\u00bb.";
    }
    return (
      "\u0417\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u00ab" +
      selectedItem.name +
      "\u00bb, \u0437\u0430\u043a\u0440\u043e\u0439\u0442\u0435 \u044f\u0447\u0435\u0439\u043a\u0443 \u0438 \u0441\u043f\u0430\u0441\u0438\u0431\u043e \u0437\u0430 \u043e\u0431\u0440\u0430\u0449\u0435\u043d\u0438\u0435."
    );
  }

  function getUnavailableUserItemMessage() {
    const selectedItem = getSelectedUserItem();
    if (!selectedItem) {
      return "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u043e\u0432\u0430\u0440 \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u043f\u043e\u043f\u044b\u0442\u043a\u0443.";
    }
    return (
      "\u0422\u043e\u0432\u0430\u0440 \u00ab" +
      selectedItem.name +
      "\u00bb \u0441\u0435\u0439\u0447\u0430\u0441 \u043d\u0435\u043b\u044c\u0437\u044f \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c. \u0412\u0435\u0440\u043d\u0438\u0442\u0435\u0441\u044c \u043a \u0441\u043f\u0438\u0441\u043a\u0443 \u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0440\u0443\u0433\u0443\u044e \u043f\u043e\u0437\u0438\u0446\u0438\u044e."
    );
  }

  function createActionButton(action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action-button action-button-" + (action.tone || "secondary");
    button.textContent = action.label;
    button.dataset.action = action.action;
    button.disabled = typeof action.disabled === "function" ? action.disabled() : Boolean(action.disabled);
    button.addEventListener("click", function () {
      handleAction(action.action);
    });
    return button;
  }

  function renderActions(screen) {
    elements.screenActions.innerHTML = "";
    screen.actions.forEach(function (action) {
      elements.screenActions.appendChild(createActionButton(action));
    });
  }

  function renderText(node, value) {
    const text = typeof value === "function" ? value() : value || "";
    node.textContent = text;
    node.classList.toggle("hidden", text === "");
  }

  function createUserItemButton(item) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "item-option";
    button.textContent = item.name;
    button.dataset.itemId = item.id;
    button.setAttribute("aria-pressed", item.id === state.selectedUserItemId ? "true" : "false");
    if (item.id === state.selectedUserItemId) {
      button.classList.add("is-selected");
    }
    button.addEventListener("click", function () {
      state.selectedUserItemId = item.id;
      showScreen("userItemSelect");
    });
    return button;
  }

  function renderUserItemSelection() {
    const screenContent = ensureScreenContent();
    screenContent.innerHTML = "";
    screenContent.classList.remove("hidden");

    if (!hasUserItems()) {
      screenContent.appendChild(
        createStatusPanel({
          tone: "empty",
          badge: "\u041d\u043e\u043c\u0435\u043d\u043a\u043b\u0430\u0442\u0443\u0440\u0430",
          heading: EMPTY_NOMENCLATURE_MESSAGE,
          detail:
            "\u041e\u0431\u0440\u0430\u0442\u0438\u0442\u0435\u0441\u044c \u043a \u0430\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440\u0443 \u0434\u043b\u044f \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0445 \u043f\u043e\u0437\u0438\u0446\u0438\u0439.",
        })
      );
      return;
    }

    const visibleItems = state.userListExpanded ? state.userItems : state.userItems.slice(0, 5);
    const list = document.createElement("div");
    list.className = "item-list" + (state.userListExpanded ? " item-list-expanded" : "");
    visibleItems.forEach(function (item) {
      list.appendChild(createUserItemButton(item));
    });
    screenContent.appendChild(list);

    if (state.userItems.length > 5) {
      const toggleButton = document.createElement("button");
      toggleButton.type = "button";
      toggleButton.className = "list-toggle-button";
      toggleButton.textContent = state.userListExpanded
        ? "\u0421\u0432\u0435\u0440\u043d\u0443\u0442\u044c \u0441\u043f\u0438\u0441\u043e\u043a"
        : "\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0432\u0435\u0441\u044c \u0441\u043f\u0438\u0441\u043e\u043a";
      toggleButton.addEventListener("click", function () {
        state.userListExpanded = !state.userListExpanded;
        showScreen("userItemSelect");
      });
      screenContent.appendChild(toggleButton);
    }
  }

  function createStatusPanel(options) {
    const panel = document.createElement("div");
    panel.className = "status-panel" + (options.tone ? " status-panel-" + options.tone : "");

    if (options.badge) {
      const badge = document.createElement("span");
      badge.className = "status-badge";
      badge.textContent = options.badge;
      panel.appendChild(badge);
    }

    if (options.heading) {
      const heading = document.createElement("p");
      heading.className = "status-heading";
      heading.textContent = options.heading;
      panel.appendChild(heading);
    }

    if (options.detail) {
      const detail = document.createElement("p");
      detail.className = "status-detail";
      detail.textContent = options.detail;
      panel.appendChild(detail);
    }

    return panel;
  }

  function renderAuthWaitingShell() {
    const screenContent = ensureScreenContent();
    screenContent.innerHTML = "";
    screenContent.classList.remove("hidden");
    screenContent.appendChild(
      createStatusPanel({
        tone: "waiting",
        badge: "RFID",
        heading: "\u0421\u0447\u0438\u0442\u044b\u0432\u0430\u0435\u043c \u043a\u0430\u0440\u0442\u0443",
        detail: "\u041f\u0440\u0438\u043b\u043e\u0436\u0438\u0442\u0435 RFID-\u043a\u0430\u0440\u0442\u0443 \u043a \u0441\u0447\u0438\u0442\u044b\u0432\u0430\u0442\u0435\u043b\u044e.",
      })
    );
  }

  function renderUserItemAvailableShell() {
    const selectedItem = getSelectedUserItem();
    const screenContent = ensureScreenContent();
    screenContent.innerHTML = "";
    screenContent.classList.remove("hidden");
    screenContent.appendChild(
      createStatusPanel({
        tone: "waiting",
        badge: "\u041f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435",
        heading: selectedItem ? selectedItem.name : "\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u0442\u043e\u0432\u0430\u0440",
        detail:
          "\u041e\u0441\u0442\u0430\u0432\u0430\u0439\u0442\u0435\u0441\u044c \u0443 \u044d\u043a\u0440\u0430\u043d\u0430. \u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u043f\u043e\u0434\u0441\u043a\u0430\u0437\u043a\u0430 \u043f\u043e\u044f\u0432\u0438\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438.",
      })
    );
  }

  function renderUserItemSuccessShell() {
    const selectedItem = getSelectedUserItem();
    const screenContent = ensureScreenContent();
    screenContent.innerHTML = "";
    screenContent.classList.remove("hidden");
    screenContent.appendChild(
      createStatusPanel({
        tone: "success",
        badge: "\u0421\u043f\u0430\u0441\u0438\u0431\u043e",
        heading: selectedItem ? selectedItem.name : "\u0422\u043e\u0432\u0430\u0440",
        detail:
          "\u0417\u0430\u0431\u0435\u0440\u0438\u0442\u0435 \u0442\u043e\u0432\u0430\u0440, \u0430\u043a\u043a\u0443\u0440\u0430\u0442\u043d\u043e \u0437\u0430\u043a\u0440\u043e\u0439\u0442\u0435 \u044f\u0447\u0435\u0439\u043a\u0443 \u0438 \u0437\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u0435 \u0440\u0430\u0431\u043e\u0442\u0443 \u043a\u043d\u043e\u043f\u043a\u043e\u0439 \u043d\u0438\u0436\u0435.",
      })
    );
  }

  function renderScreenContent(screenKey) {
    const screenContent = ensureScreenContent();
    screenContent.innerHTML = "";
    screenContent.classList.add("hidden");
    elements.screenBody.classList.toggle("screen-body-list", screenKey === "userItemSelect");

    if (screenKey === "auth") {
      renderAuthWaitingShell();
      return;
    }
    if (screenKey === "userItemSelect") {
      renderUserItemSelection();
      return;
    }
    if (screenKey === "userItemAvailable") {
      renderUserItemAvailableShell();
      return;
    }
    if (screenKey === "userItemSuccess") {
      renderUserItemSuccessShell();
    }
  }

  function showScreen(screenKey) {
    const screen = screens[screenKey];
    if (!screen) {
      return;
    }

    clearTimers();
    stopCountdown();
    hidePresenceOverlay();

    state.currentScreen = screenKey;
    elements.screenCard.dataset.roleTheme = screen.roleTheme || "default";
    renderText(elements.screenKicker, screen.kicker);
    renderText(elements.screenTitle, screen.title);
    renderText(elements.screenMessage, screen.message);
    renderScreenContent(screenKey);
    renderActions(screen);

    if (screenKey === "auth") {
      void readAndResolveRfid();
    }

    if (screen.enableIdleTimeout && canUseSharedInactivityTimeout(screenKey)) {
      scheduleIdleTimeout();
    }
    maybeScheduleAutoTransition(screenKey);
  }

  function showTimeoutPrompt() {
    if (state.isPresenceOverlayVisible || !canUseSharedInactivityTimeout(state.currentScreen)) {
      return;
    }

    clearTimers();
    stopCountdown();
    state.presencePreviousScreen = state.currentScreen;
    state.isPresenceOverlayVisible = true;
    elements.presenceOverlay.hidden = false;
    elements.presenceOverlay.setAttribute("aria-hidden", "false");
    elements.presenceOverlayCountdown.textContent = String(PRESENCE_COUNTDOWN_SECONDS);
    document.body.classList.add("presence-overlay-active");
    startCountdown(PRESENCE_COUNTDOWN_SECONDS, function () {
      handleAction("go-start");
    });
    elements.presenceOverlayYesButton.focus();
  }

  function hidePresenceOverlay() {
    state.isPresenceOverlayVisible = false;
    elements.presenceOverlay.hidden = true;
    elements.presenceOverlay.setAttribute("aria-hidden", "true");
    elements.presenceOverlayCountdown.textContent = String(PRESENCE_COUNTDOWN_SECONDS);
    document.body.classList.remove("presence-overlay-active");
  }

  function resetIdleTimeoutFromInteraction(event) {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    if (target.closest("#presence-overlay")) {
      return;
    }
    if (state.isPresenceOverlayVisible || !canUseSharedInactivityTimeout(state.currentScreen)) {
      return;
    }
    if (state.idleTimeoutId) {
      window.clearTimeout(state.idleTimeoutId);
      state.idleTimeoutId = null;
    }
    scheduleIdleTimeout();
  }

  function resolveTouchRoute(roleCode) {
    if (!roleCode || typeof roleCode !== "string") {
      return null;
    }
    return TOUCH_ROLE_ROUTES[roleCode] || null;
  }

  function showAuthError(title) {
    state.authErrorTitle = title || DEFAULT_AUTH_ERROR_TITLE;
    state.authResolvedUser = null;
    state.pendingRoutePath = null;
    showScreen("authError");
  }

  function applyResolvedTouchRoute() {
    if (state.pendingRoutePath === TOUCH_ROLE_ROUTES.user) {
      state.pendingRoutePath = null;
      showScreen("userItemSelect");
      return;
    }
    if (state.pendingRoutePath) {
      const routePath = state.pendingRoutePath;
      state.pendingRoutePath = null;
      window.location.assign(routePath);
      return;
    }
    showScreen("start");
  }

  screens.authSuccess.autoReturnAction = applyResolvedTouchRoute;

  async function readAndResolveRfid() {
    if (!AUTH_READ_AND_RESOLVE_RFID_ENDPOINT) {
      showAuthError(DEFAULT_AUTH_ERROR_TITLE);
      return;
    }

    const requestToken = state.authRequestToken + 1;
    state.authRequestToken = requestToken;

    try {
      const response = await window.fetch(AUTH_READ_AND_RESOLVE_RFID_ENDPOINT, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });

      if (state.authRequestToken !== requestToken || state.currentScreen !== "auth") {
        return;
      }

      const payload = await response.json().catch(function () {
        return {};
      });

      if (!response.ok) {
        if (response.status === 404) {
          showAuthError(DEFAULT_AUTH_ERROR_TITLE);
          return;
        }
        if (response.status === 403) {
          if (payload && (payload.detail === "User is inactive" || payload.detail === "User status is inactive")) {
            showAuthError(INACTIVE_AUTH_ERROR_TITLE);
            return;
          }
        }
        showAuthError(DEFAULT_AUTH_ERROR_TITLE);
        return;
      }

      const resolvedUser = payload && payload.user ? payload.user : null;
      const routePath = resolveTouchRoute(resolvedUser && resolvedUser.role_code);
      if (!routePath) {
        showAuthError(UNSUPPORTED_ROLE_AUTH_ERROR_TITLE);
        return;
      }

      state.authResolvedUser = resolvedUser;
      state.pendingRoutePath = routePath;
      showScreen("authSuccess");
    } catch (_error) {
      if (state.authRequestToken !== requestToken || state.currentScreen !== "auth") {
        return;
      }
      showAuthError(DEFAULT_AUTH_ERROR_TITLE);
    }
  }

  function handleAction(action) {
    if (action === "go-auth") {
      showScreen("auth");
      return;
    }
    if (action === "confirm-exit") {
      state.previousScreen = state.currentScreen;
      showScreen("exitPrompt");
      return;
    }
    if (action === "resume-previous") {
      showScreen(state.previousScreen || "start");
      return;
    }
    if (action === "go-user-item-next") {
      if (!state.selectedUserItemId) {
        showScreen("userItemSelect");
        return;
      }
      showScreen(getSelectedUserItem().isAvailable ? "userItemAvailable" : "userItemUnavailable");
      return;
    }
    if (action === "back-to-user-items") {
      showScreen("userItemSelect");
      return;
    }
    if (action === "go-start") {
      state.previousScreen = null;
      state.presencePreviousScreen = null;
      state.authResolvedUser = null;
      state.pendingRoutePath = null;
      showScreen("start");
      return;
    }
    if (action === "presence-resume") {
      const previousScreen = state.presencePreviousScreen || "start";
      state.presencePreviousScreen = null;
      showScreen(previousScreen);
    }
  }

  document.addEventListener("keydown", function (event) {
    if (!state.isPresenceOverlayVisible) {
      resetIdleTimeoutFromInteraction(event);
    }
    if (state.currentScreen === "auth" && event.key === "Escape") {
      handleAction("confirm-exit");
    }
  });

  document.addEventListener("pointerdown", resetIdleTimeoutFromInteraction, true);
  document.addEventListener("touchstart", resetIdleTimeoutFromInteraction, true);

  elements.presenceOverlayYesButton.addEventListener("click", function () {
    handleAction("presence-resume");
  });

  elements.presenceOverlayNoButton.addEventListener("click", function () {
    handleAction("go-start");
  });

  async function loadUserItems() {
    state.userItems = [];
    state.selectedUserItemId = null;
    state.userListExpanded = false;

    if (!TOUCH_NOMENCLATURE_ENDPOINT) {
      return;
    }

    try {
      const response = await window.fetch(TOUCH_NOMENCLATURE_ENDPOINT, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });
      if (!response.ok) {
        return;
      }

      const payload = await response.json();
      if (!Array.isArray(payload.nomenclature)) {
        return;
      }

      state.userItems = payload.nomenclature
        .map(function (item) {
          return {
            id: "nomenclature-" + String(item.id),
            name: String(item.name || ""),
            isAvailable: true,
          };
        })
        .filter(function (item) {
          return item.name !== "";
        });
    } catch (_error) {
      state.userItems = [];
    }
  }

  loadUserItems().finally(function () {
    showScreen("start");
  });
})();
