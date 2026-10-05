/* MakerOS client helpers (vanilla JS, no dependencies). */

// Filter the visual icon picker grid by icon name.
function makerosFilterIcons(query) {
  const q = query.trim().toLowerCase();
  document.querySelectorAll(".icon-option").forEach(function (button) {
    button.style.display = button.title.toLowerCase().includes(q) ? "" : "none";
  });
}
