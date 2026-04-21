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

  function showLanding() {
    clearTimers();
    setView("landing");
  }

  function showConfirmation() {
    clearTimers();
    setView("export-users-confirm");
  }

  function startExportUsersFlow() {
    clearTimers();
    setView("export-users-progress");
    schedule(() => {
      setView("export-users-success");
      schedule(showLanding, config.successReturnDelayMs || 2400);
    }, config.progressAdvanceDelayMs || 1800);
  }

  root.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");

    if (!target) {
      return;
    }

    const { action } = target.dataset;

    if (action === "export-users") {
      showConfirmation();
      return;
    }

    if (action === "back-to-landing") {
      showLanding();
      return;
    }

    if (action === "start-export-users") {
      startExportUsersFlow();
    }
  });

  window.addEventListener("beforeunload", clearTimers);
  showLanding();
})();
