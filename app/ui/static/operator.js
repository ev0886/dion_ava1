(function () {
  const SECTORS_PER_QUARTER = 8;
  const CELLS_PER_SECTOR = 15;
  const CELLS_PER_QUARTER = SECTORS_PER_QUARTER * CELLS_PER_SECTOR;
  const TOTAL_QUARTERS = 4;
  const REMOVE_SUCCESS_RETURN_DELAY_MS = 1800;
  const REPLENISH_SAMPLE_ITEMS = [
    { id: "item-01", name: "Вода негазированная 0,5 л", meta: "ПЭТ бутылка" },
    { id: "item-02", name: "Вода газированная 0,5 л", meta: "ПЭТ бутылка" },
    { id: "item-03", name: "Сок яблочный 0,33 л", meta: "Пакет" },
    { id: "item-04", name: "Сок апельсиновый 0,33 л", meta: "Пакет" },
    { id: "item-05", name: "Холодный чай лимон 0,5 л", meta: "ПЭТ бутылка" },
    { id: "item-06", name: "Энергетический напиток 0,25 л", meta: "Жестяная банка" },
    { id: "item-07", name: "Минеральная вода 0,75 л", meta: "ПЭТ бутылка" }
  ];

  let currentQuarter = 1;
  let activeSector = 1;
  let currentView = "board";
  let pendingAction = null;
  let pendingActionType = null;
  let isActionConfirmed = false;
  let removeSuccessTimerId = null;
  let selectedReplenishItemId = null;

  const selectedCells = new Set();

  const boardView = document.getElementById("operator-board-view");
  const confirmationView = document.getElementById("operator-confirmation-view");
  const removeExecutionView = document.getElementById("operator-remove-execution-view");
  const removeSuccessView = document.getElementById("operator-remove-success-view");
  const replenishItemSelectView = document.getElementById("operator-replenish-item-select-view");
  const replenishNextView = document.getElementById("operator-replenish-next-view");
  const mainActions = document.getElementById("operator-actions-main");
  const confirmationActions = document.getElementById("operator-actions-confirmation");
  const removeExecutionActions = document.getElementById("operator-actions-remove-execution");
  const replenishItemSelectActions = document.getElementById("operator-actions-replenish-item-select");
  const replenishNextActions = document.getElementById("operator-actions-replenish-next");
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
  const removeExecutionCount = document.getElementById("remove-execution-count");
  const removeExecutionCells = document.getElementById("remove-execution-cells");
  const removeExecutionCancelButton = document.getElementById("remove-execution-cancel-button");
  const removeExecutionCompleteButton = document.getElementById("remove-execution-complete-button");
  const replenishItemSelectCount = document.getElementById("replenish-item-select-count");
  const replenishItemSelectCells = document.getElementById("replenish-item-select-cells");
  const replenishItemList = document.getElementById("replenish-item-list");
  const replenishItemSelectCancelButton = document.getElementById("replenish-item-select-cancel-button");
  const replenishItemSelectConfirmButton = document.getElementById("replenish-item-select-confirm-button");
  const replenishNextCount = document.getElementById("replenish-next-count");
  const replenishNextItem = document.getElementById("replenish-next-item");
  const replenishNextCells = document.getElementById("replenish-next-cells");
  const replenishNextBackButton = document.getElementById("replenish-next-back-button");
  const replenishNextCloseButton = document.getElementById("replenish-next-close-button");

  if (
    !boardView ||
    !confirmationView ||
    !removeExecutionView ||
    !removeSuccessView ||
    !replenishItemSelectView ||
    !replenishNextView ||
    !mainActions ||
    !confirmationActions ||
    !removeExecutionActions ||
    !replenishItemSelectActions ||
    !replenishNextActions ||
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
    !confirmationConfirmButton ||
    !removeExecutionCount ||
    !removeExecutionCells ||
    !removeExecutionCancelButton ||
    !removeExecutionCompleteButton ||
    !replenishItemSelectCount ||
    !replenishItemSelectCells ||
    !replenishItemList ||
    !replenishItemSelectCancelButton ||
    !replenishItemSelectConfirmButton ||
    !replenishNextCount ||
    !replenishNextItem ||
    !replenishNextCells ||
    !replenishNextBackButton ||
    !replenishNextCloseButton
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

  function clearRemoveSuccessTimer() {
    if (removeSuccessTimerId !== null) {
      window.clearTimeout(removeSuccessTimerId);
      removeSuccessTimerId = null;
    }
  }

  function clearPendingActionState() {
    pendingAction = null;
    pendingActionType = null;
    isActionConfirmed = false;
    confirmationNote.hidden = true;
  }

  function syncViewState() {
    const showBoard = currentView === "board";
    const showConfirmation = currentView === "confirmation";
    const showRemoveExecution = currentView === "remove-execution";
    const showRemoveSuccess = currentView === "remove-success";
    const showReplenishItemSelect = currentView === "replenish-item-select";
    const showReplenishNext = currentView === "replenish-next";

    boardView.hidden = !showBoard;
    confirmationView.hidden = !showConfirmation;
    removeExecutionView.hidden = !showRemoveExecution;
    removeSuccessView.hidden = !showRemoveSuccess;
    replenishItemSelectView.hidden = !showReplenishItemSelect;
    replenishNextView.hidden = !showReplenishNext;
    mainActions.hidden = !showBoard;
    confirmationActions.hidden = !showConfirmation;
    removeExecutionActions.hidden = !showRemoveExecution;
    replenishItemSelectActions.hidden = !showReplenishItemSelect;
    replenishNextActions.hidden = !showReplenishNext;

    boardView.classList.toggle("is-active", showBoard);
    confirmationView.classList.toggle("is-active", showConfirmation);
    removeExecutionView.classList.toggle("is-active", showRemoveExecution);
    removeSuccessView.classList.toggle("is-active", showRemoveSuccess);
    replenishItemSelectView.classList.toggle("is-active", showReplenishItemSelect);
    replenishNextView.classList.toggle("is-active", showReplenishNext);
    mainActions.classList.toggle("is-active", showBoard);
    confirmationActions.classList.toggle("is-active", showConfirmation);
    removeExecutionActions.classList.toggle("is-active", showRemoveExecution);
    replenishItemSelectActions.classList.toggle("is-active", showReplenishItemSelect);
    replenishNextActions.classList.toggle("is-active", showReplenishNext);
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

  function renderCellChips(container) {
    const cellNumbers = getSelectedCellNumbers();
    container.innerHTML = "";

    cellNumbers.forEach(function (cellNumber) {
      const chip = document.createElement("span");
      chip.className = "confirmation-cell-chip";
      chip.textContent = String(cellNumber);
      container.appendChild(chip);
    });
  }

  function renderRemoveExecution() {
    removeExecutionCount.textContent = String(selectedCells.size);
    renderCellChips(removeExecutionCells);
  }

  function getSelectedReplenishItem() {
    return REPLENISH_SAMPLE_ITEMS.find(function (item) {
      return item.id === selectedReplenishItemId;
    }) || null;
  }

  function syncReplenishConfirmState() {
    const isReady = selectedReplenishItemId !== null;
    replenishItemSelectConfirmButton.disabled = !isReady;
    replenishItemSelectConfirmButton.classList.toggle("is-ready", isReady);
  }

  function renderReplenishItemOptions() {
    replenishItemList.innerHTML = "";

    REPLENISH_SAMPLE_ITEMS.forEach(function (item) {
      const option = document.createElement("button");
      const isSelected = item.id === selectedReplenishItemId;
      const name = document.createElement("span");
      const meta = document.createElement("span");

      option.type = "button";
      option.className = "replenish-item-option";
      option.dataset.itemId = item.id;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", isSelected ? "true" : "false");

      if (isSelected) {
        option.classList.add("is-selected");
      }

      name.className = "replenish-item-name";
      name.textContent = item.name;
      meta.className = "replenish-item-meta";
      meta.textContent = item.meta;

      option.appendChild(name);
      option.appendChild(meta);

      option.addEventListener("click", function () {
        selectedReplenishItemId = item.id;
        renderReplenishItemOptions();
        syncReplenishConfirmState();
        setStatusMessage("Пополнить: выбран товар");
      });

      replenishItemList.appendChild(option);
    });
  }

  function renderReplenishItemSelect() {
    replenishItemSelectCount.textContent = String(selectedCells.size);
    renderCellChips(replenishItemSelectCells);
    renderReplenishItemOptions();
    syncReplenishConfirmState();
  }

  function renderReplenishNext() {
    const selectedItem = getSelectedReplenishItem();

    replenishNextCount.textContent = String(selectedCells.size);
    replenishNextItem.textContent = selectedItem ? selectedItem.name : "-";
    renderCellChips(replenishNextCells);
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
    clearRemoveSuccessTimer();
    currentView = "board";
    syncViewState();
  }

  function showConfirmationView(actionType, actionLabel) {
    clearRemoveSuccessTimer();
    pendingActionType = actionType;
    pendingAction = actionLabel;
    isActionConfirmed = false;
    renderConfirmation();
    currentView = "confirmation";
    syncViewState();
  }

  function showRemoveExecutionView() {
    clearRemoveSuccessTimer();
    renderRemoveExecution();
    currentView = "remove-execution";
    syncViewState();
  }

  function showReplenishItemSelectView() {
    clearRemoveSuccessTimer();
    renderReplenishItemSelect();
    currentView = "replenish-item-select";
    syncViewState();
  }

  function showReplenishNextView() {
    clearRemoveSuccessTimer();
    renderReplenishNext();
    currentView = "replenish-next";
    syncViewState();
  }

  function returnToBoardAfterRemoveSuccess() {
    clearRemoveSuccessTimer();
    selectedCells.clear();
    clearPendingActionState();
    renderCells();
    updateSelectionSummary();
    showBoardView();
    setStatusMessage("Выберите ячейки");
  }

  function showRemoveSuccessView() {
    clearRemoveSuccessTimer();
    currentView = "remove-success";
    syncViewState();
    removeSuccessTimerId = window.setTimeout(function () {
      returnToBoardAfterRemoveSuccess();
    }, REMOVE_SUCCESS_RETURN_DELAY_MS);
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

          if (currentView === "remove-execution") {
            renderRemoveExecution();
          }

          if (currentView === "replenish-item-select") {
            renderReplenishItemSelect();
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

  function wireActionButton(button, actionType, actionLabel) {
    button.addEventListener("click", function () {
      if (selectedCells.size === 0) {
        setStatusMessage(actionLabel + ": выберите ячейки");
        return;
      }

      showConfirmationView(actionType, actionLabel);
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
    if (pendingActionType === "remove") {
      showRemoveExecutionView();
      setStatusMessage("Изъять: выполните изъятие по выбранным ячейкам");
      return;
    }

    if (pendingActionType === "refill") {
      showReplenishItemSelectView();
      setStatusMessage("Пополнить: выберите товар для выбранных ячеек");
      return;
    }

    isActionConfirmed = true;
    renderConfirmation();
  });

  removeExecutionCancelButton.addEventListener("click", function () {
    showBoardView();
    setStatusMessage("Изъять: выбор сохранен");
  });

  removeExecutionCompleteButton.addEventListener("click", function () {
    showRemoveSuccessView();
    setStatusMessage("Изъять: остатки удалены");
  });

  replenishItemSelectCancelButton.addEventListener("click", function () {
    showBoardView();
    setStatusMessage("Пополнить: выбор ячеек сохранен");
  });

  replenishItemSelectConfirmButton.addEventListener("click", function () {
    const selectedItem = getSelectedReplenishItem();

    if (!selectedItem) {
      syncReplenishConfirmState();
      return;
    }

    showReplenishNextView();
    setStatusMessage("Пополнить: подготовка к выполнению для товара " + selectedItem.name);
  });

  replenishNextBackButton.addEventListener("click", function () {
    showReplenishItemSelectView();
    setStatusMessage("Пополнить: можно изменить выбранный товар");
  });

  replenishNextCloseButton.addEventListener("click", function () {
    showBoardView();
    setStatusMessage("Пополнить: выбранный товар сохранен");
  });

  updateSelectionSummary();
  updateQuarterMeta();
  renderSectors();
  renderCells();
  syncViewState();
  wireActionButton(removeButton, "remove", "Изъять");
  wireActionButton(refillButton, "refill", "Пополнить");
})();
