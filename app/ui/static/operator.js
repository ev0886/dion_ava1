(function () {
  const SECTORS_PER_QUARTER = 8;
  const CELLS_PER_SECTOR = 15;
  const CELLS_PER_QUARTER = SECTORS_PER_QUARTER * CELLS_PER_SECTOR;
  const TOTAL_QUARTERS = 4;
  const REMOVE_SUCCESS_RETURN_DELAY_MS = 1800;
  const REPLENISH_SUCCESS_RETURN_DELAY_MS = 1800;
  const UI_IDLE_TIMEOUT_MS = 30000;
  const PRESENCE_COUNTDOWN_SECONDS = 30;
  const config = window.DION_OPERATOR_UI_CONFIG || {};
  const TOUCH_NOMENCLATURE_ENDPOINT = config.listTouchNomenclatureEndpoint || "";
  const EMPTY_NOMENCLATURE_MESSAGE = config.emptyNomenclatureMessage || "Номенклатура не настроена";
  const REPLENISH_SAMPLE_ITEMS = [];

  let currentQuarter = 1;
  let activeSector = 1;
  let currentView = "board";
  let pendingAction = null;
  let pendingActionType = null;
  let isActionConfirmed = false;
  let removeSuccessTimerId = null;
  let replenishSuccessTimerId = null;
  let inactivityTimerId = null;
  let presenceCountdownIntervalId = null;
  let presenceCountdownTimeoutId = null;
  let presenceCountdownDeadline = null;
  let presenceReturnView = null;
  let isPresenceOverlayVisible = false;
  let selectedReplenishItemId = null;

  const selectedCells = new Set();

  const boardView = document.getElementById("operator-board-view");
  const confirmationView = document.getElementById("operator-confirmation-view");
  const removeExecutionView = document.getElementById("operator-remove-execution-view");
  const removeSuccessView = document.getElementById("operator-remove-success-view");
  const replenishItemSelectView = document.getElementById("operator-replenish-item-select-view");
  const replenishExecutionView = document.getElementById("operator-replenish-execution-view");
  const replenishSuccessView = document.getElementById("operator-replenish-success-view");
  const mainActions = document.getElementById("operator-actions-main");
  const confirmationActions = document.getElementById("operator-actions-confirmation");
  const removeExecutionActions = document.getElementById("operator-actions-remove-execution");
  const replenishItemSelectActions = document.getElementById("operator-actions-replenish-item-select");
  const replenishExecutionActions = document.getElementById("operator-actions-replenish-execution");
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
  const replenishExecutionTitle = document.getElementById("replenish-execution-title");
  const replenishExecutionDescription = document.getElementById("replenish-execution-description");
  const replenishExecutionCount = document.getElementById("replenish-execution-count");
  const replenishExecutionItem = document.getElementById("replenish-execution-item");
  const replenishExecutionCells = document.getElementById("replenish-execution-cells");
  const replenishExecutionCancelButton = document.getElementById("replenish-execution-cancel-button");
  const replenishExecutionCompleteButton = document.getElementById("replenish-execution-complete-button");
  const replenishSuccessMessage = document.getElementById("replenish-success-message");
  const replenishSuccessCells = document.getElementById("replenish-success-cells");
  const presenceOverlay = document.getElementById("presence-overlay");
  const presenceOverlayCountdown = document.getElementById("presence-overlay-countdown");
  const presenceOverlayYesButton = document.getElementById("presence-overlay-yes-button");
  const presenceOverlayNoButton = document.getElementById("presence-overlay-no-button");

  if (
    !boardView ||
    !confirmationView ||
    !removeExecutionView ||
    !removeSuccessView ||
    !replenishItemSelectView ||
    !replenishExecutionView ||
    !replenishSuccessView ||
    !mainActions ||
    !confirmationActions ||
    !removeExecutionActions ||
    !replenishItemSelectActions ||
    !replenishExecutionActions ||
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
    !replenishExecutionTitle ||
    !replenishExecutionDescription ||
    !replenishExecutionCount ||
    !replenishExecutionItem ||
    !replenishExecutionCells ||
    !replenishExecutionCancelButton ||
    !replenishExecutionCompleteButton ||
    !replenishSuccessMessage ||
    !replenishSuccessCells ||
    !presenceOverlay ||
    !presenceOverlayCountdown ||
    !presenceOverlayYesButton ||
    !presenceOverlayNoButton
  ) {
    return;
  }

  function canUseSharedInactivityTimeout() {
    return currentView !== "remove-success" && currentView !== "replenish-success";
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

  function renderPresenceCountdown() {
    if (presenceCountdownDeadline === null) {
      return;
    }

    const remainingMs = Math.max(0, presenceCountdownDeadline - Date.now());
    const remainingSeconds = Math.ceil(remainingMs / 1000);
    presenceOverlayCountdown.textContent = String(remainingSeconds);
  }

  function goToStartScreen() {
    window.location.assign("/ui/user");
  }

  function hidePresenceOverlay(options) {
    const settings = options || {};

    clearPresenceCountdown();
    isPresenceOverlayVisible = false;
    presenceReturnView = null;
    presenceOverlay.hidden = true;
    presenceOverlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("presence-overlay-active");

    if (settings.restartIdleTimer !== false) {
      scheduleInactivityTimeout();
    }
  }

  function showPresenceOverlay() {
    if (isPresenceOverlayVisible || !canUseSharedInactivityTimeout()) {
      return;
    }

    clearInactivityTimer();
    clearPresenceCountdown();
    presenceReturnView = currentView;
    isPresenceOverlayVisible = true;
    presenceOverlay.hidden = false;
    presenceOverlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("presence-overlay-active");
    presenceCountdownDeadline = Date.now() + (PRESENCE_COUNTDOWN_SECONDS * 1000);
    renderPresenceCountdown();
    presenceCountdownIntervalId = window.setInterval(renderPresenceCountdown, 250);
    presenceCountdownTimeoutId = window.setTimeout(function () {
      goToStartScreen();
    }, PRESENCE_COUNTDOWN_SECONDS * 1000);
    presenceOverlayYesButton.focus();
  }

  function scheduleInactivityTimeout() {
    clearInactivityTimer();

    if (isPresenceOverlayVisible || !canUseSharedInactivityTimeout()) {
      return;
    }

    inactivityTimerId = window.setTimeout(function () {
      showPresenceOverlay();
    }, UI_IDLE_TIMEOUT_MS);
  }

  function restartInactivityTimeout() {
    if (isPresenceOverlayVisible) {
      return;
    }

    scheduleInactivityTimeout();
  }

  function handlePresenceResume() {
    if (!isPresenceOverlayVisible) {
      return;
    }

    if (presenceReturnView && currentView !== presenceReturnView) {
      currentView = presenceReturnView;
      syncViewState();
    }

    hidePresenceOverlay({ restartIdleTimer: true });
  }

  function handlePresenceInteraction(event) {
    const target = event.target;

    if (!(target instanceof Element)) {
      return;
    }

    if (target.closest("#presence-overlay")) {
      return;
    }

    restartInactivityTimeout();
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

  function getSectorCellNumbers(quarter, sectorNumber) {
    const sectorStart = getQuarterSectorStart(quarter);
    const columnIndex = sectorNumber - sectorStart;

    if (columnIndex < 0 || columnIndex >= SECTORS_PER_QUARTER) {
      return [];
    }

    const cellNumbers = [];

    for (let rowIndex = 0; rowIndex < CELLS_PER_SECTOR; rowIndex += 1) {
      cellNumbers.push(getVisibleCellNumber(quarter, columnIndex, rowIndex));
    }

    return cellNumbers;
  }

  function isSectorFullySelected(quarter, sectorNumber) {
    const sectorCellNumbers = getSectorCellNumbers(quarter, sectorNumber);

    return (
      sectorCellNumbers.length === CELLS_PER_SECTOR &&
      sectorCellNumbers.every(function (cellNumber) {
        return selectedCells.has(cellNumber);
      })
    );
  }

  function getSelectedCellNumbers() {
    return Array.from(selectedCells).sort(function (left, right) {
      return left - right;
    });
  }

  function getQuarterForCellNumber(cellNumber) {
    return Math.floor((cellNumber - 1) / CELLS_PER_QUARTER) + 1;
  }

  function getSelectedQuarter() {
    const firstSelectedCell = selectedCells.values().next();
    if (firstSelectedCell.done) {
      return null;
    }

    return getQuarterForCellNumber(firstSelectedCell.value);
  }

  function prepareSelectionForQuarter(targetQuarter) {
    const selectedQuarter = getSelectedQuarter();

    if (selectedQuarter !== null && selectedQuarter !== targetQuarter) {
      selectedCells.clear();
      return true;
    }

    return false;
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

  function clearReplenishSuccessTimer() {
    if (replenishSuccessTimerId !== null) {
      window.clearTimeout(replenishSuccessTimerId);
      replenishSuccessTimerId = null;
    }
  }

  function clearPendingActionState(options) {
    const settings = options || {};

    pendingAction = null;
    pendingActionType = null;
    isActionConfirmed = false;
    confirmationNote.hidden = true;

    if (settings.preserveSelectedReplenishItem !== true) {
      selectedReplenishItemId = null;
    }
  }

  function syncViewState() {
    const showBoard = currentView === "board";
    const showConfirmation = currentView === "confirmation";
    const showRemoveExecution = currentView === "remove-execution";
    const showRemoveSuccess = currentView === "remove-success";
    const showReplenishItemSelect = currentView === "replenish-item-select";
    const showReplenishExecution = currentView === "replenish-execution";
    const showReplenishSuccess = currentView === "replenish-success";

    boardView.hidden = !showBoard;
    confirmationView.hidden = !showConfirmation;
    removeExecutionView.hidden = !showRemoveExecution;
    removeSuccessView.hidden = !showRemoveSuccess;
    replenishItemSelectView.hidden = !showReplenishItemSelect;
    replenishExecutionView.hidden = !showReplenishExecution;
    replenishSuccessView.hidden = !showReplenishSuccess;
    mainActions.hidden = !showBoard;
    confirmationActions.hidden = !showConfirmation;
    removeExecutionActions.hidden = !showRemoveExecution;
    replenishItemSelectActions.hidden = !showReplenishItemSelect;
    replenishExecutionActions.hidden = !showReplenishExecution;

    boardView.classList.toggle("is-active", showBoard);
    confirmationView.classList.toggle("is-active", showConfirmation);
    removeExecutionView.classList.toggle("is-active", showRemoveExecution);
    removeSuccessView.classList.toggle("is-active", showRemoveSuccess);
    replenishItemSelectView.classList.toggle("is-active", showReplenishItemSelect);
    replenishExecutionView.classList.toggle("is-active", showReplenishExecution);
    replenishSuccessView.classList.toggle("is-active", showReplenishSuccess);
    mainActions.classList.toggle("is-active", showBoard);
    confirmationActions.classList.toggle("is-active", showConfirmation);
    removeExecutionActions.classList.toggle("is-active", showRemoveExecution);
    replenishItemSelectActions.classList.toggle("is-active", showReplenishItemSelect);
    replenishExecutionActions.classList.toggle("is-active", showReplenishExecution);
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

  function hasReplenishItems() {
    return REPLENISH_SAMPLE_ITEMS.length > 0;
  }

  function syncReplenishConfirmState() {
    const isReady = selectedReplenishItemId !== null;
    replenishItemSelectConfirmButton.disabled = !isReady;
    replenishItemSelectConfirmButton.classList.toggle("is-ready", isReady);
  }

  function renderReplenishItemOptions() {
    replenishItemList.innerHTML = "";

    if (!hasReplenishItems()) {
      const emptyState = document.createElement("div");
      emptyState.className = "replenish-item-empty-state";
      emptyState.textContent = EMPTY_NOMENCLATURE_MESSAGE;
      replenishItemList.appendChild(emptyState);
      return;
    }

    REPLENISH_SAMPLE_ITEMS.forEach(function (item) {
      const option = document.createElement("button");
      const isSelected = item.id === selectedReplenishItemId;
      const name = document.createElement("span");

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

      option.appendChild(name);

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

  function renderReplenishExecution() {
    const selectedItem = getSelectedReplenishItem();
    const itemName = selectedItem ? selectedItem.name : "item #";

    replenishExecutionTitle.textContent =
      "Осуществите пополнение остатков выбранных ячеек товаром " + itemName;
    replenishExecutionDescription.textContent =
      "Товар " + itemName + " выбран для пополнения выбранных ячеек.";
    replenishExecutionCount.textContent = String(selectedCells.size);
    replenishExecutionItem.textContent = itemName;
    renderCellChips(replenishExecutionCells);
  }

  function renderReplenishSuccess() {
    const selectedItem = getSelectedReplenishItem();
    const itemName = selectedItem ? selectedItem.name : "item #";

    replenishSuccessMessage.textContent =
      "Выбранные ячейки успешно пополнены товаром " + itemName;
    renderCellChips(replenishSuccessCells);
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
    clearReplenishSuccessTimer();
    currentView = "board";
    syncViewState();
    scheduleInactivityTimeout();
  }

  function showConfirmationView(actionType, actionLabel) {
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    pendingActionType = actionType;
    pendingAction = actionLabel;
    isActionConfirmed = false;
    renderConfirmation();
    currentView = "confirmation";
    syncViewState();
    scheduleInactivityTimeout();
  }

  function showRemoveExecutionView() {
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    renderRemoveExecution();
    currentView = "remove-execution";
    syncViewState();
    scheduleInactivityTimeout();
  }

  function showReplenishItemSelectView() {
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    renderReplenishItemSelect();
    currentView = "replenish-item-select";
    syncViewState();
    scheduleInactivityTimeout();
  }

  function showReplenishExecutionView() {
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    renderReplenishExecution();
    currentView = "replenish-execution";
    syncViewState();
    scheduleInactivityTimeout();
  }

  function returnToBoardAfterRemoveSuccess() {
    clearRemoveSuccessTimer();
    selectedCells.clear();
    clearPendingActionState();
    renderSectors();
    renderCells();
    updateSelectionSummary();
    showBoardView();
    setStatusMessage("Выберите ячейки");
  }

  function showRemoveSuccessView() {
    hidePresenceOverlay({ restartIdleTimer: false });
    clearInactivityTimer();
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    currentView = "remove-success";
    syncViewState();
    removeSuccessTimerId = window.setTimeout(function () {
      returnToBoardAfterRemoveSuccess();
    }, REMOVE_SUCCESS_RETURN_DELAY_MS);
  }

  function returnToBoardAfterReplenishSuccess() {
    clearReplenishSuccessTimer();
    selectedCells.clear();
    clearPendingActionState();
    renderSectors();
    renderCells();
    updateSelectionSummary();
    showBoardView();
    setStatusMessage("Выберите ячейки");
  }

  function showReplenishSuccessView() {
    hidePresenceOverlay({ restartIdleTimer: false });
    clearInactivityTimer();
    clearRemoveSuccessTimer();
    clearReplenishSuccessTimer();
    renderReplenishSuccess();
    currentView = "replenish-success";
    syncViewState();
    replenishSuccessTimerId = window.setTimeout(function () {
      returnToBoardAfterReplenishSuccess();
    }, REPLENISH_SUCCESS_RETURN_DELAY_MS);
  }

  function renderSectors() {
    sectorGrid.innerHTML = "";

    for (let index = 0; index < SECTORS_PER_QUARTER; index += 1) {
      const sectorNumber = getQuarterSectorStart(currentQuarter) + index;
      const isActiveSector = sectorNumber === activeSector;
      const isFullySelected = isSectorFullySelected(currentQuarter, sectorNumber);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sector-chip";
      button.textContent = String(sectorNumber);
      button.dataset.sector = String(sectorNumber);
      button.setAttribute("aria-label", "Сектор " + sectorNumber);
      button.setAttribute("aria-pressed", isActiveSector ? "true" : "false");
      button.setAttribute("aria-selected", isFullySelected ? "true" : "false");

      if (isActiveSector) {
        button.classList.add("is-active");
      }

      if (isFullySelected) {
        button.classList.add("is-fully-selected");
      }

      button.addEventListener("click", function () {
        const sectorCellNumbers = getSectorCellNumbers(currentQuarter, sectorNumber);
        const shouldClearSector = sectorCellNumbers.every(function (cellNumber) {
          return selectedCells.has(cellNumber);
        });
        const didClearPreviousQuarter = !shouldClearSector && prepareSelectionForQuarter(currentQuarter);

        activeSector = sectorNumber;

        sectorCellNumbers.forEach(function (cellNumber) {
          if (shouldClearSector) {
            selectedCells.delete(cellNumber);
          } else {
            selectedCells.add(cellNumber);
          }
        });

        renderSectors();
        renderCells();
        updateSelectionSummary();

        if (shouldClearSector) {
          setStatusMessage("Сектор " + sectorNumber + " снят");
        } else {
          setStatusMessage("Сектор " + sectorNumber + " выбран полностью");
        }
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
            prepareSelectionForQuarter(currentQuarter);
            selectedCells.add(cellNumber);
            button.classList.add("is-selected");
            button.setAttribute("aria-pressed", "true");
            setStatusMessage("Ячейка " + cellNumber + " выбрана");
          }

          updateSelectionSummary();
          renderSectors();
          renderCells();

          if (currentView === "confirmation") {
            renderConfirmation();
          }

          if (currentView === "remove-execution") {
            renderRemoveExecution();
          }

          if (currentView === "replenish-item-select") {
            renderReplenishItemSelect();
          }

          if (currentView === "replenish-execution") {
            renderReplenishExecution();
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

    showReplenishExecutionView();
    setStatusMessage("Пополнить: выполните пополнение для товара " + selectedItem.name);
  });

  replenishExecutionCancelButton.addEventListener("click", function () {
    showBoardView();
    setStatusMessage("Пополнить: выбор ячеек сохранен");
  });

  replenishExecutionCompleteButton.addEventListener("click", function () {
    const selectedItem = getSelectedReplenishItem();

    showReplenishSuccessView();
    setStatusMessage(
      "Пополнить: выбранные ячейки пополнены" +
        (selectedItem ? " товаром " + selectedItem.name : "")
    );
  });

  updateSelectionSummary();
  updateQuarterMeta();
  renderSectors();
  renderCells();
  syncViewState();
  wireActionButton(removeButton, "remove", "Изъять");
  wireActionButton(refillButton, "refill", "Пополнить");
  presenceOverlayYesButton.addEventListener("click", function () {
    handlePresenceResume();
  });

  presenceOverlayNoButton.addEventListener("click", function () {
    goToStartScreen();
  });

  document.addEventListener("pointerdown", handlePresenceInteraction, true);
  document.addEventListener("keydown", function (event) {
    if (isPresenceOverlayVisible) {
      return;
    }

    handlePresenceInteraction(event);
  }, true);
  document.addEventListener("touchstart", handlePresenceInteraction, true);

  async function loadReplenishItems() {
    REPLENISH_SAMPLE_ITEMS.splice(0, REPLENISH_SAMPLE_ITEMS.length);
    selectedReplenishItemId = null;

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

      payload.nomenclature.forEach(function (item) {
        if (!item || !item.name) {
          return;
        }
        REPLENISH_SAMPLE_ITEMS.push({
          id: "nomenclature-" + String(item.id),
          name: String(item.name),
        });
      });
    } catch (error) {
      REPLENISH_SAMPLE_ITEMS.splice(0, REPLENISH_SAMPLE_ITEMS.length);
    }
  }

  loadReplenishItems().finally(function () {
    scheduleInactivityTimeout();
  });
})();
