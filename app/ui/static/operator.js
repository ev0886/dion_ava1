(function () {
  const SECTORS_PER_QUARTER = 8;
  const CELLS_PER_SECTOR = 15;
  const CELLS_PER_QUARTER = SECTORS_PER_QUARTER * CELLS_PER_SECTOR;
  const TOTAL_QUARTERS = 4;

  let currentQuarter = 1;
  let activeSector = 1;
  let currentView = "board";
  let pendingAction = null;
  let isActionConfirmed = false;

  const selectedCells = new Set();

  const boardView = document.getElementById("operator-board-view");
  const confirmationView = document.getElementById("operator-confirmation-view");
  const mainActions = document.getElementById("operator-actions-main");
  const confirmationActions = document.getElementById("operator-actions-confirmation");
  const sectorGrid = document.getElementById("sector-grid");
  const cellsGrid = document.getElementById("cells-grid");
  const selectionSummary = document.getElementById("selection-summary");
  const statusMessage = document.getElementById("status-message");
  const operatorSummary = document.getElementById("operator-summary");
  const quarterIndicator = document.getElementById("quarter-indicator");
  const quarterPrev = document.getElementById("quarter-prev");
  const quarterNext = document.getElementById("quarter-next");
  const removeButton = document.getElementById("remove-button");
  const refillButton = document.getElementById("refill-button");
  const confirmationAction = document.getElementById("confirmation-action");
  const confirmationCount = document.getElementById("confirmation-count");
  const confirmationCells = document.getElementById("confirmation-cells");
  const confirmationKicker = document.getElementById("confirmation-kicker");
  const confirmationTitle = document.getElementById("confirmation-title");
  const confirmationNote = document.getElementById("confirmation-note");
  const confirmationBackButton = document.getElementById("confirmation-back-button");
  const confirmationConfirmButton = document.getElementById("confirmation-confirm-button");

  if (
    !boardView ||
    !confirmationView ||
    !mainActions ||
    !confirmationActions ||
    !sectorGrid ||
    !cellsGrid ||
    !selectionSummary ||
    !statusMessage ||
    !operatorSummary ||
    !quarterIndicator ||
    !quarterPrev ||
    !quarterNext ||
    !removeButton ||
    !refillButton ||
    !confirmationAction ||
    !confirmationCount ||
    !confirmationCells ||
    !confirmationKicker ||
    !confirmationTitle ||
    !confirmationNote ||
    !confirmationBackButton ||
    !confirmationConfirmButton
  ) {
    return;
  }

  function getQuarterCellStart(quarter) {
    return (quarter - 1) * CELLS_PER_QUARTER + 1;
  }

  function getQuarterSectorStart(quarter) {
    return (quarter - 1) * SECTORS_PER_QUARTER + 1;
  }

  function getVisibleCellNumber(quarter, columnIndex, rowIndex) {
    return getQuarterCellStart(quarter) + columnIndex * CELLS_PER_SECTOR + rowIndex;
  }

  function getSelectedCellNumbers() {
    return Array.from(selectedCells).sort(function (left, right) {
      return left - right;
    });
  }

  function updateSelectionSummary() {
    selectionSummary.textContent = "Выбрано: " + selectedCells.size;
  }

  function setStatusMessage(message) {
    statusMessage.textContent = message;
  }

  function updateQuarterMeta() {
    const sectorStart = getQuarterSectorStart(currentQuarter);
    const sectorEnd = sectorStart + SECTORS_PER_QUARTER - 1;
    const cellStart = getQuarterCellStart(currentQuarter);
    const cellEnd = cellStart + CELLS_PER_QUARTER - 1;

    operatorSummary.textContent =
      "Секторы " + sectorStart + "-" + sectorEnd + " • Ячейки " + cellStart + "-" + cellEnd;
    quarterIndicator.textContent = currentQuarter + "/4";
  }

  function syncViewState() {
    const showBoard = currentView === "board";

    boardView.hidden = !showBoard;
    confirmationView.hidden = showBoard;
    mainActions.hidden = !showBoard;
    confirmationActions.hidden = showBoard;

    boardView.classList.toggle("is-active", showBoard);
    confirmationView.classList.toggle("is-active", !showBoard);
    mainActions.classList.toggle("is-active", showBoard);
    confirmationActions.classList.toggle("is-active", !showBoard);
  }

  function renderConfirmationCells() {
    const cellNumbers = getSelectedCellNumbers();

    confirmationCells.innerHTML = "";

    cellNumbers.forEach(function (cellNumber) {
      const chip = document.createElement("span");
      chip.className = "confirmation-cell-chip";
      chip.textContent = String(cellNumber);
      confirmationCells.appendChild(chip);
    });
  }

  function renderConfirmation() {
    confirmationAction.textContent = pendingAction || "-";
    confirmationCount.textContent = String(selectedCells.size);
    confirmationKicker.textContent = pendingAction || "Подтверждение";
    confirmationTitle.textContent = isActionConfirmed ? "Действие подтверждено" : "Подтвердите действие";
    confirmationNote.hidden = !isActionConfirmed;
    renderConfirmationCells();
  }

  function showBoardView() {
    currentView = "board";
    syncViewState();
  }

  function showConfirmationView(actionLabel) {
    pendingAction = actionLabel;
    isActionConfirmed = false;
    renderConfirmation();
    currentView = "confirmation";
    syncViewState();
  }

  function renderSectors() {
    sectorGrid.innerHTML = "";

    for (let index = 0; index < SECTORS_PER_QUARTER; index += 1) {
      const sectorNumber = getQuarterSectorStart(currentQuarter) + index;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sector-chip";
      button.textContent = String(index + 1);
      button.dataset.sector = String(sectorNumber);
      button.setAttribute("aria-label", "Сектор " + sectorNumber);
      button.setAttribute("aria-pressed", sectorNumber === activeSector ? "true" : "false");

      if (sectorNumber === activeSector) {
        button.classList.add("is-active");
      }

      button.addEventListener("click", function () {
        activeSector = sectorNumber;
        renderSectors();
        setStatusMessage("Сектор " + sectorNumber + " выбран");
      });

      sectorGrid.appendChild(button);
    }
  }

  function renderCells() {
    cellsGrid.innerHTML = "";

    for (let rowIndex = 0; rowIndex < CELLS_PER_SECTOR; rowIndex += 1) {
      for (let columnIndex = 0; columnIndex < SECTORS_PER_QUARTER; columnIndex += 1) {
        const cellNumber = getVisibleCellNumber(currentQuarter, columnIndex, rowIndex);
        const button = document.createElement("button");

        button.type = "button";
        button.className = "cell-button";
        button.dataset.cell = String(cellNumber);
        button.setAttribute("role", "gridcell");
        button.setAttribute("aria-pressed", selectedCells.has(cellNumber) ? "true" : "false");
        button.setAttribute("aria-label", "Ячейка " + cellNumber);
        button.textContent = String(cellNumber);

        if (selectedCells.has(cellNumber)) {
          button.classList.add("is-selected");
        }

        button.addEventListener("click", function () {
          if (selectedCells.has(cellNumber)) {
            selectedCells.delete(cellNumber);
            button.classList.remove("is-selected");
            button.setAttribute("aria-pressed", "false");
            setStatusMessage("Ячейка " + cellNumber + " снята");
          } else {
            selectedCells.add(cellNumber);
            button.classList.add("is-selected");
            button.setAttribute("aria-pressed", "true");
            setStatusMessage("Ячейка " + cellNumber + " выбрана");
          }

          updateSelectionSummary();

          if (currentView === "confirmation") {
            renderConfirmation();
          }
        });

        cellsGrid.appendChild(button);
      }
    }
  }

  function setQuarter(nextQuarter) {
    currentQuarter = nextQuarter;
    activeSector = getQuarterSectorStart(currentQuarter);
    updateQuarterMeta();
    renderSectors();
    renderCells();
    setStatusMessage("Четверть " + currentQuarter + "/4");
  }

  function wireActionButton(button, actionLabel) {
    button.addEventListener("click", function () {
      if (selectedCells.size === 0) {
        setStatusMessage(actionLabel + ": выберите ячейки");
        return;
      }

      showConfirmationView(actionLabel);
    });
  }

  quarterPrev.addEventListener("click", function () {
    const nextQuarter = currentQuarter === 1 ? TOTAL_QUARTERS : currentQuarter - 1;
    setQuarter(nextQuarter);
  });

  quarterNext.addEventListener("click", function () {
    const nextQuarter = currentQuarter === TOTAL_QUARTERS ? 1 : currentQuarter + 1;
    setQuarter(nextQuarter);
  });

  confirmationBackButton.addEventListener("click", function () {
    showBoardView();
    if (pendingAction) {
      setStatusMessage(pendingAction + ": выбор сохранен");
    }
  });

  confirmationConfirmButton.addEventListener("click", function () {
    isActionConfirmed = true;
    renderConfirmation();
  });

  updateSelectionSummary();
  updateQuarterMeta();
  renderSectors();
  renderCells();
  syncViewState();
  wireActionButton(removeButton, "Изъять");
  wireActionButton(refillButton, "Пополнить");
})();
