(function () {
  const elements = {
    statusPanel: document.getElementById("status-panel"),
    statusTitle: document.getElementById("status-title"),
    statusMessage: document.getElementById("status-message"),
    adminLastSync: document.getElementById("admin-last-sync"),
    adminRouteTableBody: document.getElementById("admin-route-table-body"),
    adminCallouts: document.getElementById("admin-callouts")
  };

  const routeRows = [
    {
      route: "/ui/user",
      purpose: "Пользовательский kiosk-flow для авторизации и выдачи",
      focus: "Крупные действия, RFID, быстрый выбор товара"
    },
    {
      route: "/ui/mvp",
      purpose: "Алиас пользовательского экрана без отдельного визуального отклонения",
      focus: "Та же фирменная подача, что и на /ui/user"
    },
    {
      route: "/ui/operator",
      purpose: "Touch-first пополнение по четвертям барабана",
      focus: "Quarter paging, cell grid, batch selection, staged confirmation"
    },
    {
      route: "/ui/admin",
      purpose: "Административный обзор и сервисная координация",
      focus: "Контроль маршрутов, границ ролей и контекста обслуживания"
    }
  ];

  const callouts = [
    {
      title: "Без смешивания ролей",
      body: "Операторский маршрут не возвращается к desktop-таблице и не сливается с административной консолью."
    },
    {
      title: "Фирменная палитра",
      body: "Восстановлены зеленый, белый и нейтральные оттенки вместо упрощенных placeholder-страниц."
    },
    {
      title: "UI-фокус ветки",
      body: "Ветка концентрируется на визуальном и touch workflow слое без внедрения реального drum-control поведения."
    }
  ];

  function setStatus(kind, title, message) {
    elements.statusPanel.className = "status-panel" + (kind ? " status-" + kind : "");
    elements.statusTitle.textContent = title;
    elements.statusMessage.textContent = message;
  }

  function renderRoutes() {
    elements.adminRouteTableBody.innerHTML = routeRows.map(function (row) {
      return "<tr><td><strong>" + row.route + "</strong></td><td>" + row.purpose + "</td><td>" + row.focus + "</td></tr>";
    }).join("");
  }

  function renderCallouts() {
    elements.adminCallouts.innerHTML = callouts.map(function (callout) {
      return '<article class="callout-card"><h2>' + callout.title + "</h2><p>" + callout.body + "</p></article>";
    }).join("");
  }

  elements.adminLastSync.textContent = new Date().toLocaleString("ru-RU");
  renderRoutes();
  renderCallouts();
  setStatus("success", "Готово", "Административный экран снова выглядит как часть общей фирменной системы и остается отдельным от operator UI.");
})();
