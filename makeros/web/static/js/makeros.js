/* MakerOS client helpers (vanilla JS, no dependencies). */

// Filter the visual icon picker grid by icon name.
function makerosFilterIcons(query) {
  var q = query.trim().toLowerCase();
  document.querySelectorAll(".icon-option").forEach(function (button) {
    button.style.display = button.title.toLowerCase().includes(q) ? "" : "none";
  });
}

// Mobile off-canvas sidebar.
function makerosToggleSidebar(toggle) {
  var open = document.body.classList.toggle("sidebar-open");
  if (toggle) {
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.setAttribute(
      "aria-label",
      open ? "Cerrar menú" : "Abrir menú"
    );
  }
}

// Card density steps: 1 Compacta, 2 Normal, 3 Detallada, 4 Completa.
// Each step widens the card and reveals more elements (CSS hides
// .step-2/3/4 classes below the active step). Text size never changes.
var CARD_STEPS = {
  1: "Compacta",
  2: "Normal",
  3: "Detallada",
  4: "Completa",
};

function makerosCardSize(value) {
  var step = Math.min(4, Math.max(1, parseInt(value, 10) || 2));
  document.querySelectorAll(".card-grid").forEach(function (grid) {
    grid.dataset.step = step;
  });
  document.querySelectorAll(".card-size-input").forEach(function (slider) {
    slider.value = step;
  });
  document.querySelectorAll("[data-step-label]").forEach(function (label) {
    label.textContent = CARD_STEPS[step];
  });
  try {
    localStorage.setItem("makeros-card-step", step);
  } catch (e) {
    /* private mode: keep it session-only */
  }
}

// Obsidian-style "/" block menu inside editor textareas.
document.addEventListener("input", function (event) {
  var input = event.target;
  if (!input || !input.hasAttribute || !input.hasAttribute("data-slash-input")) return;
  var menu = input.parentElement.querySelector("[data-slash-menu]");
  if (!menu) return;
  var value = input.value;
  var query = null;
  if (value === "/") {
    query = "";
  } else if (value.length > 1 && value.indexOf("/") === 0 &&
             value.indexOf("\n") === -1 && input.selectionStart === value.length) {
    query = value.slice(1).toLowerCase();
  }
  if (query === null) {
    menu.hidden = true;
    return;
  }
  var any = false;
  menu.querySelectorAll(".slash-item").forEach(function (item) {
    var label = item.querySelector("span").textContent.toLowerCase();
    var show = !query || label.indexOf(query) !== -1 || item.dataset.tipo.indexOf(query) !== -1;
    item.style.display = show ? "" : "none";
    any = any || show;
  });
  menu.hidden = !any;
});

// Pick a block from the slash menu: replace "/" with the block seed.
document.addEventListener("click", function (event) {
  var item = event.target.closest ? event.target.closest(".slash-item") : null;
  if (!item) return;
  event.preventDefault();
  var menu = item.closest("[data-slash-menu]");
  var input = menu.parentElement.querySelector("[data-slash-input]");
  input.value = JSON.parse(item.dataset.seed);
  menu.hidden = true;
  input.focus();
});

// Esc closes the slash menu; clicking outside closes any open one.
document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;
  document.querySelectorAll("[data-slash-menu]").forEach(function (menu) {
    menu.hidden = true;
  });
});
document.addEventListener("click", function (event) {
  document.querySelectorAll("[data-slash-menu]").forEach(function (menu) {
    if (!menu.hidden && !menu.parentElement.contains(event.target)) {
      menu.hidden = true;
    }
  });
});

// Restore the saved card density step on load, then wire kanban drag.
document.addEventListener("DOMContentLoaded", function () {
  var step = 2;
  try {
    step = localStorage.getItem("makeros-card-step") || 2;
  } catch (e) {
    step = 2;
  }
  makerosCardSize(step);

  if (typeof Sortable === "undefined" || !document.querySelector(".kanban")) {
    return;
  }
  document.querySelectorAll(".kanban").forEach(function (board) {
    board.querySelectorAll(".kanban-cards").forEach(function (column) {
      Sortable.create(column, {
        group: "kanban-" + board.dataset.group,
        animation: 150,
        onEnd: function (event) {
          var path = event.item.dataset.path;
          var status = event.to.dataset.status;
          fetch("/" + path + "/estado", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: "estado=" + encodeURIComponent(status),
          }).catch(function () {
            location.reload();  // restore the true state on failure
          });
        },
      });
    });
  });
});
