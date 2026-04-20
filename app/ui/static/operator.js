(function () {
  const totalCells = 120;
  const selectedCells = new Set();

  const sectorGrid = document.getElementById("sector-grid");
  const cellsGrid = document.getElementById("cells-grid");
  const selectionSummary = document.getElementById("selection-summary");
  const statusMessage = document.getElementById("status-message");
  const removeButton = document.getElementById("remove-button");
  const refillButton = document.getElementById("refill-button");

  if (!sectorGrid || !cellsGrid || !selectionSummary || !statusMessage || !removeButton || !refillButton) {
    return;
  }

  function formatCellNumber(cellNumber) {
    return String(cellNumber).padStart(3, "0");
  }

  function updateSelectionSummary() {
    selectionSummary.textContent = "Выбрано ячеек: " + selectedCells.size;
  }

  function setStatusMessage(message) {
    statusMessage.textContent = message;
  }

  function renderSectors() {
    const sectors = [
      { id: 1, label: "Сектор 1", range: "001-030" },
      { id: 2, label: "Сектор 2", range: "031-060" },
      { id: 3, label: "Сектор 3", range: "061-090" },
      { id: 4, label: "Сектор 4", range: "091-120" },
    ];

    sectors.forEach(function (sector, index) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sector-chip";
      button.dataset.sector = String(sector.id);
      button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      if (index === 0) {
        button.classList.add("is-active");
      }
      button.innerHTML = "<strong>" + sector.label + "</strong><span>" + sector.range + "</span>";
      button.addEventListener("click", function () {
        sectorGrid.querySelectorAll(".sector-chip").forEach(function (chip) {
          chip.classList.remove("is-active");
          chip.setAttribute("aria-pressed", "false");
        });
        button.classList.add("is-active");
        button.setAttribute("aria-pressed", "true");
        setStatusMessage(sector.label + " выбран.");
      });
      sectorGrid.appendChild(button);
    });
  }

  function renderCells() {
    for (let cellNumber = 1; cellNumber <= totalCells; cellNumber += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "cell-button";
      button.dataset.cell = String(cellNumber);
      button.setAttribute("role", "gridcell");
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", "Ячейка " + formatCellNumber(cellNumber));
      button.innerHTML =
        '<span class="cell-button-content">' +
        '<span class="cell-number">' + cellNumber + "</span>" +
        '<span class="cell-label">ячейка</span>' +
        "</span>";

      button.addEventListener("click", function () {
        const isSelected = selectedCells.has(cellNumber);

        if (isSelected) {
          selectedCells.delete(cellNumber);
          button.classList.remove("is-selected");
          button.setAttribute("aria-pressed", "false");
          setStatusMessage("Ячейка " + formatCellNumber(cellNumber) + " снята с выделения.");
        } else {
          selectedCells.add(cellNumber);
          button.classList.add("is-selected");
          button.setAttribute("aria-pressed", "true");
          setStatusMessage("Ячейка " + formatCellNumber(cellNumber) + " выбрана.");
        }

        updateSelectionSummary();
      });

      cellsGrid.appendChild(button);
    }
  }

  function wirePlaceholderAction(button, actionLabel) {
    button.addEventListener("click", function () {
      if (selectedCells.size === 0) {
        setStatusMessage(actionLabel + ": выберите хотя бы одну ячейку.");
        return;
      }

      setStatusMessage(
        actionLabel +
          ": выбрано " +
          selectedCells.size +
          " ячеек. Подтвердите следующее действие на следующем экране."
      );
    });
  }

  renderSectors();
  renderCells();
  updateSelectionSummary();
  wirePlaceholderAction(removeButton, "Изъять");
  wirePlaceholderAction(refillButton, "Пополнить");
})();
