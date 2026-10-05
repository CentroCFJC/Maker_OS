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

// Card-grid density slider (per-browser preference).
function makerosCardSize(value) {
  document.querySelectorAll(".card-grid").forEach(function (grid) {
    grid.style.setProperty("--card-min", value + "px");
  });
  try {
    localStorage.setItem("makeros-card-min", value);
  } catch (e) {
    /* private mode: keep it session-only */
  }
}

document.addEventListener("DOMContentLoaded", function () {
  var saved = null;
  try {
    saved = localStorage.getItem("makeros-card-min");
  } catch (e) {
    saved = null;
  }
  if (saved) {
    document.querySelectorAll(".card-size-input").forEach(function (slider) {
      slider.value = saved;
    });
    makerosCardSize(saved);
  }
});
