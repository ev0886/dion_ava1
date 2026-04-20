(function () {
  const SECTORS_PER_QUARTER = 8;
  const CELLS_PER_SECTOR = 15;
  const CELLS_PER_QUARTER = SECTORS_PER_QUARTER * CELLS_PER_SECTOR;
  const TOTAL_QUARTERS = 4;

  let currentQuarter = 1;
  let activeSector = 1;

  const selectedCells = new Set();

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

  if (
    !sectorGrid ||
    !cellsGrid ||
    !selectionSummary ||
    !statusMessage ||
    !operatorSummary ||
    !quarterIndicator ||
    !quarterPrev ||
    !quarterNext ||
    !removeButton ||
    !refillButton
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

  function wirePlaceholderAction(button, actionLabel) {
    button.addEventListener("click", function () {
      if (selectedCells.size === 0) {
        setStatusMessage(actionLabel + ": выберите ячейки");
        return;
      }

      setStatusMessage(actionLabel + ": выбрано " + selectedCells.size);
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

  updateSelectionSummary();
  updateQuarterMeta();
  renderSectors();
  renderCells();
  wirePlaceholderAction(removeButton, "Изъять");
  wirePlaceholderAction(refillButton, "Пополнить");
})();
