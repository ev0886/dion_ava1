(function () {
  const config = window.DION_UI_CONFIG || {};

  const elements = {
    screenKicker: document.getElementById("screen-kicker"),
    screenTitle: document.getElementById("screen-title"),
    screenMessage: document.getElementById("screen-message"),
    countdownPanel: document.getElementById("countdown-panel"),
    countdownValue: document.getElementById("countdown-value"),
    screenActions: document.getElementById("screen-actions"),
    screenCard: document.querySelector(".screen-card"),
  };

  const state = {
    currentScreen: "start",
    previousScreen: null,
    idleTimeoutId: null,
    delayedTransitionId: null,
    countdownIntervalId: null,
    countdownTimeoutId: null,
    countdownDeadline: null,
  };

  const screens = {
    start: {
      title: "\u0413\u043e\u0442\u043e\u0432 \u043a \u0432\u044b\u0434\u0430\u0447\u0435",
      actions: [
        { label: "\u041d\u0430\u0447\u0430\u0442\u044c", action: "go-auth", tone: "primary" },
      ],
    },
    auth: {
      title: "\u041f\u0440\u0438\u043b\u043e\u0436\u0438\u0442\u0435 \u043a\u0430\u0440\u0442\u0443",
      actions: [
        { label: "\u0423\u0441\u043f\u0435\u0448\u043d\u043e", action: "auth-success", tone: "primary" },
        { label: "\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d", action: "auth-error", tone: "secondary" },
        { label: "\u0412\u044b\u0439\u0442\u0438", action: "confirm-exit", tone: "ghost" },
      ],
      enableIdleTimeout: true,
    },
    authError: {
      title: "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d",
      autoReturnMs: config.authErrorReturnTimeoutMs,
      actions: [],
    },
    authSuccess: {
      title: "\u0423\u0441\u043f\u0435\u0448\u043d\u043e!",
      autoReturnMs: config.authSuccessRouteDelayMs,
      actions: [],
    },
    roleSelect: {
      kicker: "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0435\u0436\u0438\u043c",
      title: "\u041a\u0443\u0434\u0430 \u043f\u0435\u0440\u0435\u0439\u0442\u0438?",
      message: "\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u0435 \u0440\u0430\u0431\u043e\u0442\u0443 \u0432 \u043d\u0443\u0436\u043d\u043e\u043c \u0440\u0430\u0437\u0434\u0435\u043b\u0435.",
      actions: [
        { label: "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c", action: "go-user-role", tone: "primary" },
        { label: "\u041e\u043f\u0435\u0440\u0430\u0442\u043e\u0440", action: "go-operator-role", tone: "secondary" },
        { label: "\u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440", action: "go-admin-role", tone: "ghost" },
        { label: "\u0412\u044b\u0439\u0442\u0438", action: "confirm-exit", tone: "ghost" },
      ],
      enableIdleTimeout: true,
      roleTheme: "role-select",
    },
    userHome: {
      kicker: "\u041f\u0440\u0438\u0432\u0435\u0442\u0441\u0442\u0432\u0438\u0435",
      title: "\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c",
      message: "\u0412\u044b \u043c\u043e\u0436\u0435\u0442\u0435 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u0440\u0430\u0431\u043e\u0442\u0443 \u0432 \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u043c \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0438.",
      actions: [
        { label: "\u041d\u0430 \u0433\u043b\u0430\u0432\u043d\u0443\u044e", action: "go-start", tone: "primary" },
      ],
      enableIdleTimeout: true,
      roleTheme: "user",
    },
    timeoutPrompt: {
      title: "\u0412\u044b \u0435\u0449\u0435 \u0437\u0434\u0435\u0441\u044c?",
      countdownSeconds: config.presenceCountdownSeconds,
      actions: [
        { label: "\u0414\u0430", action: "resume-previous", tone: "primary" },
        { label: "\u041d\u0435\u0442", action: "go-start", tone: "secondary" },
      ],
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

  function renderCountdown() {
    if (!state.countdownDeadline) {
      return;
    }

    const remainingMs = Math.max(0, state.countdownDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    elements.countdownValue.textContent = String(remainingSeconds);
  }

  function stopCountdown() {
    elements.countdownPanel.classList.add("hidden");
    elements.countdownValue.textContent = "0";
  }

  function startCountdown(durationSeconds, onExpire) {
    state.countdownDeadline = Date.now() + durationSeconds * 1000;
    elements.countdownPanel.classList.remove("hidden");
    renderCountdown();
    state.countdownIntervalId = window.setInterval(renderCountdown, 250);
    state.countdownTimeoutId = window.setTimeout(onExpire, durationSeconds * 1000);
  }

  function scheduleIdleTimeout() {
    if (!config.uiIdleTimeoutMs) {
      return;
    }

    state.idleTimeoutId = window.setTimeout(function () {
      showTimeoutPrompt();
    }, config.uiIdleTimeoutMs);
  }

  function maybeScheduleAutoTransition(screenKey) {
    const screen = screens[screenKey];
    if (!screen || !screen.autoReturnMs) {
      return;
    }

    state.delayedTransitionId = window.setTimeout(function () {
      if (screenKey === "authSuccess") {
        showScreen("roleSelect");
        return;
      }
      showScreen("start");
    }, screen.autoReturnMs);
  }

  function createActionButton(action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action-button action-button-" + (action.tone || "secondary");
    button.textContent = action.label;
    button.dataset.action = action.action;
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
    const text = value || "";
    node.textContent = text;
    node.classList.toggle("hidden", text === "");
  }

  function showScreen(screenKey) {
    const screen = screens[screenKey];
    if (!screen) {
      return;
    }

    clearTimers();
    stopCountdown();

    state.currentScreen = screenKey;
    elements.screenCard.dataset.roleTheme = screen.roleTheme || "default";
    renderText(elements.screenKicker, screen.kicker);
    elements.screenTitle.textContent = screen.title;
    renderText(elements.screenMessage, screen.message);
    renderActions(screen);

    if (screen.enableIdleTimeout) {
      scheduleIdleTimeout();
    }
    maybeScheduleAutoTransition(screenKey);
  }

  function showTimeoutPrompt() {
    if (state.currentScreen === "start" || state.currentScreen === "timeoutPrompt") {
      return;
    }

    state.previousScreen = state.currentScreen;
    showScreen("timeoutPrompt");
    startCountdown(config.presenceCountdownSeconds, function () {
      showScreen("start");
    });
  }

  function handleAction(action) {
    if (action === "go-auth") {
      showScreen("auth");
      return;
    }
    if (action === "auth-success") {
      showScreen("authSuccess");
      return;
    }
    if (action === "auth-error") {
      showScreen("authError");
      return;
    }
    if (action === "go-user-role") {
      showScreen("userHome");
      return;
    }
    if (action === "go-operator-role") {
      window.location.assign("/ui/operator");
      return;
    }
    if (action === "go-admin-role") {
      window.location.assign("/ui/admin");
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
    if (action === "go-start") {
      showScreen("start");
    }
  }

  document.addEventListener("keydown", function (event) {
    if (state.currentScreen !== "auth") {
      return;
    }

    if (event.key === "s" || event.key === "S") {
      handleAction("auth-success");
      return;
    }
    if (event.key === "e" || event.key === "E") {
      handleAction("auth-error");
      return;
    }
    if (event.key === "Escape") {
      handleAction("confirm-exit");
    }
  });

  showScreen("start");
})();
