const Toast = (() => {
  const rootId = "toast-root";
  const icons = {
    info: "i",
    success: "+",
    warning: "!",
    error: "x",
    mate: "#",
  };

  function ensureRoot() {
    let root = document.getElementById(rootId);
    if (!root) {
      root = document.createElement("div");
      root.id = rootId;
      document.body.appendChild(root);
    }
    return root;
  }

  function dismiss(node) {
    if (!node) {
      return;
    }
    node.classList.remove("in");
    node.classList.add("out");
    node.addEventListener(
      "animationend",
      () => {
        if (node.parentElement) {
          node.parentElement.removeChild(node);
        }
      },
      { once: true }
    );
  }

  function show(message, type = "info", options = {}) {
    const { timeout = 2800, persist = false } = options;
    const root = ensureRoot();
    const toast = document.createElement("div");
    const icon = document.createElement("span");
    const text = document.createElement("div");
    const close = document.createElement("button");

    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "status");

    icon.className = "toast-icon";
    icon.textContent = icons[type] || icons.info;

    text.className = "toast-text";
    text.textContent = message;

    close.className = "toast-close";
    close.type = "button";
    close.setAttribute("aria-label", "Close notification");
    close.innerHTML = "&times;";
    close.addEventListener("click", () => dismiss(toast));

    toast.append(icon, text, close);
    root.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("in"));

    if (!persist) {
      window.setTimeout(() => dismiss(toast), timeout);
    }

    return toast;
  }

  return { show, dismiss };
})();

const state = {
  selectedPiece: null,
  promotionOpen: false,
  requestInFlight: false,
};

const dom = {};

function qs(selector, root = document) {
  return root.querySelector(selector);
}

function qsa(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

function cacheDom() {
  dom.body = document.body;
  dom.cells = qsa(".chess-board td");
  dom.turnValue = qs(".turn-display span");
  dom.statusTitle = qs("#status-title");
  dom.statusCopy = qs("#status-copy");
  dom.moveControls = qs("#move-controls");
  dom.promotionForm = qs(".promotion-form");
  dom.promotionSelect = qs("#promotion_piece");
  dom.castleButton = qs("#btn-castle");
  dom.resetButton = qs("#btn-reset");
}

function setTurn(turn) {
  if (dom.turnValue) {
    dom.turnValue.textContent = turn;
  }
  if (dom.body) {
    dom.body.dataset.turn = turn;
  }
}

function isPlayersTurn() {
  return document.body.dataset.turn === "player";
}

function setBusy(isBusy) {
  state.requestInFlight = isBusy;
  document.body.dataset.busy = isBusy ? "true" : "false";
  if (dom.castleButton) {
    dom.castleButton.disabled = isBusy;
  }
  if (dom.resetButton) {
    dom.resetButton.disabled = isBusy;
  }
  if (dom.promotionSelect) {
    dom.promotionSelect.disabled = isBusy;
  }
  if (dom.promotionForm) {
    const submitButton = qs('button[type="submit"]', dom.promotionForm);
    if (submitButton) {
      submitButton.disabled = isBusy;
    }
  }
}

function renderStatus(title, copy) {
  if (dom.statusTitle) {
    dom.statusTitle.textContent = title;
  }
  if (dom.statusCopy) {
    dom.statusCopy.textContent = copy;
  }
}

function syncControls() {
  if (dom.moveControls) {
    dom.moveControls.hidden = state.promotionOpen;
  }
  if (dom.promotionForm) {
    dom.promotionForm.hidden = !state.promotionOpen;
  }
}

function showPromotionForm() {
  state.promotionOpen = true;
  syncControls();
  renderStatus("Promotion required", "Choose a piece to finish the move.");
  if (dom.promotionSelect) {
    dom.promotionSelect.focus();
  }
}

function hidePromotionForm() {
  state.promotionOpen = false;
  syncControls();
  if (isPlayersTurn()) {
    renderStatus("Your move", "Select one of your pieces, then click the destination square.");
  } else {
    renderStatus("Bot is thinking", "Waiting for the engine to reply.");
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });

  let data = {};
  try {
    data = await response.json();
  } catch (_error) {
    data = {};
  }

  if (!response.ok) {
    throw new Error(data.status || `HTTP ${response.status}`);
  }

  return data;
}

function resetGame() {
  if (state.requestInFlight) {
    return;
  }
  window.location.href = "/";
}

function clearSelection() {
  state.selectedPiece = null;
  dom.cells.forEach((cell) => cell.classList.remove("selected"));
}

function selectCell(cell, piece) {
  clearSelection();
  state.selectedPiece = piece;
  cell.classList.add("selected");
  renderStatus("Piece selected", "Choose a destination square, or click another of your pieces to change selection.");
}

function updateBoard(board, turn, botWhite) {
  dom.cells.forEach((cell, index) => {
    const piece = board[index];
    if (!piece) {
      cell.innerHTML = "";
      return;
    }

    const type = piece[0].toLowerCase();
    const colorClass = piece[0] === piece[0].toUpperCase() ? "black-piece" : "white-piece";
    cell.innerHTML = `<img src="/static/icons/${type}.svg" class="piece ${colorClass}" alt="${piece}">`;
  });

  if (typeof botWhite === "boolean") {
    document.body.dataset.botwhite = String(botWhite);
  }
  setTurn(turn);
}

function notifyCheckIfAny(response) {
  if (response?.in_check) {
    Toast.show(`${response.turn.toUpperCase()} is in check.`, "warning", { timeout: 2200 });
  }
}

function describeError(status) {
  switch (status) {
    case "invalid":
      return "That move is not legal.";
    case "invalid-castle":
      return "Castling is not legal in this position.";
    case "self-check":
      return "That move leaves your king in check.";
    case "game-over":
      return "The game is already over.";
    case "no-session":
      return "Your session expired. Starting a new game.";
    default:
      return "Something went wrong.";
  }
}

function scheduleReset(message, timeout = 1400) {
  if (message) {
    Toast.show(message, "mate", { timeout });
  }
  window.setTimeout(resetGame, timeout);
}

function handleTerminalState(response) {
  if (response.status === "checkmate") {
    renderStatus("Checkmate", `${response.winner || "Unknown"} wins.`);
    scheduleReset(`Checkmate! Winner: ${response.winner || "unknown"}`, 1800);
    return true;
  }

  if (response.status === "stalemate") {
    renderStatus("Stalemate", "No legal moves remain.");
    Toast.show("Stalemate. Draw.", "info", { timeout: 1800 });
    window.setTimeout(resetGame, 1400);
    return true;
  }

  return false;
}

async function requestAndHandle(url, payload) {
  if (state.requestInFlight) {
    return null;
  }

  setBusy(true);
  try {
    const response = await postJson(url, payload);
    updateBoard(response.board, response.turn, response.botWhite);
    clearSelection();
    return response;
  } catch (error) {
    if (error.message === "no-session") {
      Toast.show(describeError(error.message), "error", { timeout: 2200 });
      window.setTimeout(resetGame, 600);
    } else {
      Toast.show(describeError(error.message), "error", { timeout: 2400 });
      renderStatus("Action failed", describeError(error.message));
    }
    return null;
  } finally {
    setBusy(false);
  }
}

async function botMove() {
  renderStatus("Bot is thinking", "Waiting for the engine to reply.");
  const response = await requestAndHandle("/bot_move");
  if (!response) {
    return;
  }

  if (handleTerminalState(response)) {
    return;
  }

  if (response.status === "success") {
    notifyCheckIfAny(response);
    renderStatus("Your move", "Select one of your pieces, then click the destination square.");
    return;
  }

  if (response.status === "error") {
    Toast.show("Bot could not find a valid move.", "error", { timeout: 2200 });
    renderStatus("Engine error", "The bot did not return a legal reply.");
  }
}

async function sendPromotion(choice) {
  const response = await requestAndHandle("/promote", { piece: choice });
  if (!response) {
    return;
  }

  hidePromotionForm();

  if (handleTerminalState(response)) {
    return;
  }

  if (response.status === "promoted") {
    Toast.show("Pawn promoted.", "success", { timeout: 1600 });
    notifyCheckIfAny(response);
    if (response.turn === "bot") {
      await botMove();
    }
  }
}

async function makeMove(moveInput) {
  const response = await requestAndHandle("/make_move", { move: moveInput });
  if (!response) {
    return;
  }

  if (handleTerminalState(response)) {
    return;
  }

  switch (response.status) {
    case "success":
    case "castle":
      notifyCheckIfAny(response);
      if (response.turn === "bot") {
        await botMove();
      }
      break;
    case "promote":
      Toast.show("Pawn reached the last rank.", "info", { timeout: 2200 });
      showPromotionForm();
      break;
    default:
      Toast.show(describeError(response.status), "error", { timeout: 2400 });
      renderStatus("Illegal move", describeError(response.status));
      break;
  }
}

function onBoardClick(cell) {
  if (state.requestInFlight || state.promotionOpen || !isPlayersTurn()) {
    return;
  }

  const image = qs("img", cell);
  const piece = image ? image.getAttribute("alt") : null;
  const cellIndex = Number.parseInt(cell.dataset.index || cell.id.split("-")[1], 10);

  if (!state.selectedPiece) {
    if (!piece || piece[0] !== piece[0].toLowerCase()) {
      return;
    }
    selectCell(cell, piece);
    return;
  }

  if (piece && piece[0] === piece[0].toLowerCase()) {
    selectCell(cell, piece);
    return;
  }

  const moveInput = `${state.selectedPiece} ${cellIndex}`;
  clearSelection();
  makeMove(moveInput);
}

function castleMove() {
  if (state.requestInFlight || state.promotionOpen || !isPlayersTurn()) {
    return;
  }
  makeMove("castle");
}

function hydrateGithubLinks() {
  qsa(".github-link").forEach((link) => {
    const url = link.getAttribute("data-url") ||
                link.getAttribute("href") ||
                "";
    const match = url.match(/github\.com\/([^\/]+)\/?$/);
    if (match) {
      link.textContent = match[1];
    }
  });
}

function bindEvents() {
  dom.cells.forEach((cell) => {
    cell.addEventListener("click", () => onBoardClick(cell));
  });

  if (dom.castleButton) {
    dom.castleButton.addEventListener("click", castleMove);
  }

  if (dom.resetButton) {
    dom.resetButton.addEventListener("click", resetGame);
  }

  if (dom.promotionForm) {
    dom.promotionForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const choice = (dom.promotionSelect?.value || "QUEEN").toUpperCase();
      sendPromotion(choice);
    });
  }
}

function initializeStatus() {
  state.promotionOpen = Boolean(dom.promotionForm && !dom.promotionForm.hidden);
  syncControls();

  if (state.promotionOpen) {
    renderStatus("Promotion required", "Choose a piece to finish the move.");
    return;
  }

  if (isPlayersTurn()) {
    renderStatus("Your move", "Select one of your pieces, then click the destination square.");
  } else {
    renderStatus("Bot is thinking", "Waiting for the engine to reply.");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  cacheDom();
  bindEvents();
  hydrateGithubLinks();
  initializeStatus();
});

window.resetGame = resetGame;
window.castleMove = castleMove;
