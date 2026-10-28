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

// Dark / light mode, per browser (localStorage), default from the OS.
function makerosToggleTheme(button) {
  var root = document.documentElement;
  var next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  try {
    localStorage.setItem("makeros-theme", next);
  } catch (e) {
    /* private mode: keep it for this page only */
  }
  if (button) {
    makerosPaintThemeToggle(next);
  }
}

function makerosPaintThemeToggle(theme) {
  var icon = document.getElementById("theme-toggle-icon");
  var label = document.getElementById("theme-toggle-label");
  var button = document.getElementById("theme-toggle");
  if (!icon || !label) return;
  icon.setAttribute(
    "href",
    theme === "dark"
      ? "/static/vendor/feather-sprite.svg#sun"
      : "/static/vendor/feather-sprite.svg#moon"
  );
  label.textContent = theme === "dark" ? "Modo claro" : "Modo oscuro";
  if (button) {
    button.setAttribute(
      "aria-label",
      theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"
    );
  }
}

// On load, paint the toggle to match the restored theme.
document.addEventListener("DOMContentLoaded", function () {
  makerosPaintThemeToggle(document.documentElement.dataset.theme || "light");
});

// Admin panel tabs. The active tab is kept in the URL hash so a
// redirect (form post) or reload lands back on the same tab.
function makerosAdminTab(name) {
  var valid = document.querySelector('.admin-tab[data-tab="' + name + '"]');
  if (!valid) name = "usuarios";
  document.querySelectorAll(".admin-tab").forEach(function (panel) {
    var active = panel.dataset.tab === name;
    panel.classList.toggle("active", active);
    panel.setAttribute("aria-hidden", active ? "false" : "true");
  });
  document.querySelectorAll(".admin-tab-button").forEach(function (button) {
    var active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  try {
    history.replaceState(null, "", "#" + name);
  } catch (e) {
    /* ignore */
  }
}

document.addEventListener("DOMContentLoaded", function () {
  if (!document.querySelector(".admin-tabs")) return;
  var hash = decodeURIComponent(location.hash.slice(1));
  makerosAdminTab(hash || "usuarios");
});

// Theme buttons (admin Apariencia tab): apply instantly in the
// browser, then persist through the server endpoint in background.
function makerosApplyTheme(kind, value, button) {
  var body = document.body;
  var accent = kind === "accent" ? value : (body.dataset.accent || "rojo");
  var bg = kind === "bg" ? value : (body.dataset.bg || "blanco");

  // Instant visual change, before the server answers.
  body.dataset.accent = accent;
  body.dataset.bg = bg;

  document.querySelectorAll("[data-theme-accent]").forEach(function (el) {
    var active = el.dataset.themeAccent === accent;
    el.classList.toggle("active", active);
    el.setAttribute("aria-pressed", active ? "true" : "false");
  });
  document.querySelectorAll("[data-theme-bg]").forEach(function (el) {
    var active = el.dataset.themeBg === bg;
    el.classList.toggle("active", active);
    el.setAttribute("aria-pressed", active ? "true" : "false");
  });

  fetch("/admin/tema", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "accent=" + encodeURIComponent(accent) + "&fondo=" + encodeURIComponent(bg),
  }).then(function (response) {
    makerosThemeStatus(response.ok ? "Guardado." : "No se pudo guardar.");
  }).catch(function () {
    makerosThemeStatus("No se pudo guardar (sin conexión).");
  });
}

function makerosThemeStatus(text) {
  var status = document.getElementById("theme-status");
  if (!status) return;
  status.textContent = text;
  status.classList.add("visible");
  setTimeout(function () { status.classList.remove("visible"); }, 2500);
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
          // A drag also fires a click; block the quick-edit popup for it.
          window.makerosKanbanDragged = true;
          setTimeout(function () { window.makerosKanbanDragged = false; }, 150);
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

// Block editor: upload an image and drop the markdown at the cursor.
function makerosUploadBlockImage(input) {
  var file = input.files && input.files[0];
  if (!file) return;
  var wrap = input.closest(".block-form");
  var status = wrap.querySelector("[data-upload-status]");
  var textarea = wrap.querySelector("textarea[name=text]");
  var url = wrap.getAttribute("hx-post").replace(/\/bloques\/\d+\/editar$/, "/imagenes");
  status.textContent = "Subiendo…";
  var data = new FormData();
  data.append("archivo", file);
  fetch(url, { method: "POST", body: data })
    .then(function (response) {
      if (!response.ok) throw new Error("subida rechazada");
      return response.json();
    })
    .then(function (payload) {
      var alt = payload.name.replace(/\.[a-z0-9]+$/i, "");
      var markdown = "![" + alt + "](" + payload.url + ")";
      makerosReplaceImageSeed(textarea, markdown);
      status.textContent = "Imagen añadida — Guardar para verla.";
    })
    .catch(function () {
      status.textContent = "No se pudo subir la imagen.";
    });
  input.value = "";
}

// Block editor: set/replace the size token on the first image alt.
function makerosSetImageSize(select) {
  var wrap = select.closest(".block-form");
  var textarea = wrap.querySelector("textarea[name=text]");
  var size = select.value;
  var m = textarea.value.match(/^!\[([^\]]*)\]\(([^)]+)\)/);
  if (!m) return;
  var alt = m[1];
  alt = alt.split("|")[0].trim() + (size ? "|" + size : "");
  textarea.value = "![" + alt + "](" + m[2] + ")" + textarea.value.slice(m[0].length);
}

// Block editor: insert an image from a pasted URL (banner-style).
function makerosInsertImageUrl(button) {
  var input = button.parentElement.querySelector(".block-image-url");
  var url = (input.value || "").trim();
  var status = button.parentElement.querySelector("[data-upload-status]");
  if (!/^https?:\/\//.test(url)) {
    status.textContent = "Pega una URL http(s) válida.";
    return;
  }
  var wrap = button.closest(".block-form");
  var textarea = wrap.querySelector("textarea[name=text]");
  var alt = decodeURIComponent(url.split("/").pop() || "imagen").replace(/\.[a-z0-9]+$/i, "");
  var markdown = "![" + alt + "](" + url + ")";
  makerosReplaceImageSeed(textarea, markdown);
  input.value = "";
  status.textContent = "Imagen añadida — Guardar para verla.";
}

// An image block holds ONE image: the seed placeholder goes away the
// moment a real one arrives (this killed the duplicated block text).
function makerosReplaceImageSeed(textarea, markdown) {
  var value = textarea.value;
  var seed = value.match(/!\[Descripción de la imagen\]\([^)]*\)/);
  if (seed) {
    textarea.value = value.replace(seed[0], markdown);
  } else if (/^!\[/.test(value.trim())) {
    textarea.value = markdown;  // replacing a previous image outright
  } else {
    var at = textarea.selectionStart || textarea.value.length;
    textarea.value = value.slice(0, at) + markdown + value.slice(at);
  }
}

// Image blocks: wrap the <img> with a resize handle. Drag the corner,
// the width snaps to one of the four sizes and is saved to the block.
function makerosWireImageResize(root) {
  root.querySelectorAll(".block-content img").forEach(function (img) {
    if (img.dataset.resizable) return;
    img.dataset.resizable = "1";
    var wrap = document.createElement("span");
    wrap.className = "img-wrap";
    img.parentNode.insertBefore(wrap, img);
    wrap.appendChild(img);
    var handle = document.createElement("span");
    handle.className = "img-handle";
    handle.title = "Arrastra para cambiar el tamaño";
    wrap.appendChild(handle);
    handle.addEventListener("mousedown", function (event) {
      makerosDragImageSize(event, img);
    });
  });
}

function makerosDragImageSize(event, img) {
  event.preventDefault();
  var block = img.closest(".block");
  var container = img.closest(".block-content");
  var containerW = container.clientWidth || 1;
  var startX = event.clientX;
  var startPct = ((img.clientWidth || containerW) / containerW) * 100;
  var pct = startPct;

  function onMove(move) {
    // Freeform: as tiny as the handle stays grabbable (5%).
    pct = Math.min(100, Math.max(5, startPct + ((move.clientX - startX) / containerW) * 100));
    img.style.maxWidth = "none";
    img.style.width = pct + "%";
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    var best = [Math.round(pct), String(Math.round(pct))];
    var index = block.id.replace("block-", "");
    var base = block.dataset.pageUrl;
    if (!base) return;
    fetch(base + "/bloques/" + index + "/tamano", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "tamano=" + encodeURIComponent(best[1]),
    }).then(function (response) {
      if (!response.ok) throw new Error("save failed");
      return response.text();
    }).then(function (html) {
      var tmp = document.createElement("div");
      tmp.innerHTML = html;
      var fresh = tmp.firstElementChild;
      block.replaceWith(fresh);
      makerosWireImageResize(fresh);
    }).catch(function () {
      // Keep the dragged size visually, note the save failure.
      var note = document.createElement("p");
      note.className = "block-upload-status";
      note.textContent = "No se pudo guardar el tamaño.";
      block.appendChild(note);
    });
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

document.addEventListener("DOMContentLoaded", function () {
  makerosWireImageResize(document);
});
document.addEventListener("htmx:afterSwap", function (event) {
  makerosWireImageResize(event.target);
});

// Sidebar collapse: icon-only rail, remembered per browser.
function makerosToggleSidebar(button) {
  var root = document.documentElement;
  var collapsed = root.dataset.sidebar === "collapsed";
  if (collapsed) {
    delete root.dataset.sidebar;
  } else {
    root.dataset.sidebar = "collapsed";
  }
  try {
    localStorage.setItem(
      "makeros-sidebar", collapsed ? "expanded" : "collapsed"
    );
  } catch (e) { /* private mode */ }
  makerosPaintSidebarToggle(!collapsed);
}

function makerosPaintSidebarToggle(collapsed) {
  var icon = document.getElementById("sidebar-collapse-icon");
  var button = document.getElementById("sidebar-collapse");
  if (!icon || !button) return;
  icon.setAttribute(
    "href",
    collapsed
      ? "/static/vendor/feather-sprite.svg#chevrons-right"
      : "/static/vendor/feather-sprite.svg#chevrons-left"
  );
  var label = collapsed ? "Expandir el menú lateral" : "Contraer el menú lateral";
  button.setAttribute("aria-label", label);
  button.title = label;
}

document.addEventListener("DOMContentLoaded", function () {
  makerosPaintSidebarToggle(document.documentElement.dataset.sidebar === "collapsed");
  var sidebar = document.querySelector(".sidebar");
  if (sidebar) {
    sidebar.addEventListener("click", function (event) {
      if (document.documentElement.dataset.sidebar !== "collapsed") return;
      // Clicks on real controls do their thing; empty rail space expands.
      if (event.target.closest("a, button, form, input, select, textarea, details")) return;
      makerosToggleSidebar(document.getElementById("sidebar-collapse"));
    });
  }
});

/* ---------- Global modal (creation/edit popups) ---------- */
var makerosModalPending = 0;

function makerosProcessModal() {
  var body = document.getElementById("makeros-modal-body");
  if (!body) return;
  if (window.htmx) { htmx.process(body); return; }
  // htmx loads deferred; retry until it arrives, then wire the fragment.
  var tries = 0;
  var timer = setInterval(function () {
    if (window.htmx || ++tries > 50) {
      clearInterval(timer);
      if (window.htmx) htmx.process(body);
    }
  }, 100);
}

function makerosCloseModal() {
  var dialog = document.getElementById("makeros-modal");
  if (dialog && dialog.open) dialog.close();
}

function makerosOpenModal(url, title) {
  var dialog = document.getElementById("makeros-modal");
  if (!dialog) { window.location = url; return; }
  var body = document.getElementById("makeros-modal-body");
  var head = document.getElementById("makeros-modal-title");
  head.textContent = title || "";
  body.innerHTML = '<p class="modal-loading">Cargando…</p>';
  if (!dialog.open) dialog.showModal();
  var ticket = ++makerosModalPending;
  fetch(url, { headers: { "X-MakerOS-Modal": "1" } })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
    .then(function (html) {
      if (ticket !== makerosModalPending) return;  // superseded
      body.innerHTML = html;
      // Critical: innerHTML injection bypasses htmx — without this the
      // form's hx-post stays inert and "Crear" silently does a native GET.
      makerosProcessModal();
      if (!head.textContent) {
        var formTitle = body.querySelector("[data-modal-title]");
        head.textContent = formTitle ? formTitle.textContent : "";
      }
    })
    .catch(function () {
      if (ticket !== makerosModalPending) return;
      body.innerHTML = '<p class="modal-error">No se pudo abrir el formulario.</p>';
    });
}

document.addEventListener("DOMContentLoaded", function () {
  var dialog = document.getElementById("makeros-modal");
  if (!dialog) return;
  dialog.addEventListener("click", function (e) {
    // Click on the backdrop (the dialog itself) closes the modal.
    if (e.target === dialog) makerosCloseModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") makerosCloseModal();
  });
});

/* htmx: modal forms swap their response into the modal body; the
   server returns a tiny script that closes and reloads on success. */
document.addEventListener("htmx:responseError", function (e) {
  var body = document.getElementById("makeros-modal-body");
  if (!body || !e.target.closest(".modal-form")) return;
  var detail = "";
  try { detail = JSON.parse(e.detail.xhr.responseText).detail || ""; } catch (err) { /* keep */ }
  var banner = document.createElement("p");
  banner.className = "modal-error";
  banner.textContent = detail || "No se pudo guardar.";
  var existing = body.querySelector(".modal-error");
  if (existing) existing.remove();
  body.insertBefore(banner, body.firstChild);
});

/* True right after a kanban drag, so the card click that follows it
   doesn't pop the quick-edit modal. */
function makerosKanbanDragBlocked() {
  if (window.makerosKanbanDragged) {
    window.makerosKanbanDragged = false;
    return true;
  }
  return false;
}

/* ---------- Obsidian-style live block editing ---------- */
var makerosBlockFlow = null;  // "next" | "next-new" | "close"

// Click a rendered block -> edit it in place (links and controls navigate).
document.addEventListener("click", function (e) {
  if (e.defaultPrevented) return;
  var content = e.target.closest(".block-content");
  if (!content || !content.dataset.editUrl) return;
  if (e.target.closest("a, button, form, input, textarea, select, details")) return;
  e.preventDefault();
  htmx.ajax("GET", content.dataset.editUrl,
            { target: content.closest(".block"), swap: "outerHTML" });
});

function makerosAutoresize(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight + 2, 480) + "px";
}

document.addEventListener("input", function (e) {
  if (e.target.matches && e.target.matches(".block-form textarea")) makerosAutoresize(e.target);
});

// Autosize on open (htmx swaps the form in).
document.addEventListener("htmx:afterSwap", function (e) {
  var ta = e.detail.target.querySelector && e.detail.target.querySelector(".block-form textarea");
  if (ta) { makerosAutoresize(ta); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
});

document.addEventListener("keydown", function (e) {
  var form = e.target.closest && e.target.closest(".block-form");
  if (!form || e.target.tagName !== "TEXTAREA") return;
  var menu = form.querySelector("[data-slash-menu]");
  var menuOpen = menu && !menu.hidden;

  if (e.key === "Enter" && menuOpen) {
    e.preventDefault();
    var pick = Array.prototype.find.call(
      menu.querySelectorAll(".slash-item"),
      function (el) { return el.style.display !== "none"; }
    );
    if (pick) pick.click();
    return;
  }
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
    // Line change: save, render, continue in the next block.
    e.preventDefault();
    form.dataset.flow = "next";
    htmx.trigger(form, "submit");
  } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    form.dataset.flow = "close";
    htmx.trigger(form, "submit");
  } else if (e.key === "Escape" && !menuOpen) {
    e.preventDefault();
    form.dataset.flow = "close";
    htmx.trigger(form, "submit");
  }
});

// Leaving the editor saves (buttons inside the form don't count as blur).
document.addEventListener("focusout", function (e) {
  var form = e.target.closest && e.target.closest(".block-form");
  if (!form || e.target.tagName !== "TEXTAREA") return;
  setTimeout(function () {
    if (form.contains(document.activeElement)) return;
    if (form.dataset.submitting) return;
    form.dataset.submitting = "1";
    form.dataset.flow = "close";
    htmx.trigger(form, "submit");
  }, 120);
});

// After a save: continue the flow into the next block (or a fresh one).
document.addEventListener("htmx:beforeRequest", function (e) {
  if (e.target.classList && e.target.classList.contains("block-form") && e.target.dataset.flow) {
    makerosBlockFlow = e.target.dataset.flow;
    delete e.target.dataset.flow;
  }
});

function makerosOpenEditor(block) {
  var content = block.querySelector(".block-content");
  if (!content || !content.dataset.editUrl) return;
  htmx.ajax("GET", content.dataset.editUrl, { target: block, swap: "outerHTML" });
}

document.addEventListener("htmx:afterSwap", function (e) {
  if (!makerosBlockFlow) return;
  var mode = makerosBlockFlow;
  makerosBlockFlow = null;
  if (mode === "close") return;

  if (mode === "next-new") {
    var blocks = e.detail.target.querySelectorAll(".block");
    if (blocks.length) makerosOpenEditor(blocks[blocks.length - 1]);
    return;
  }
  var block = e.detail.target.closest ? (e.detail.target.closest(".block") ||
               e.detail.target.querySelector(".block")) : null;
  if (!block) return;
  var next = block.nextElementSibling;
  while (next && !next.classList.contains("block")) next = next.nextElementSibling;
  if (next) {
    makerosOpenEditor(next);
  } else {
    // End of the page: keep writing in a brand-new block.
    makerosBlockFlow = "next-new";
    htmx.ajax("POST", block.dataset.pageUrl + "/bloques/nuevo",
              { target: document.querySelector(".blocks"), swap: "beforeend",
                values: { tipo: "parrafo", despues: "-1" } });
  }
});

/* ---------- Tag filter (cards with data-tags, chips with data-tag) ---------- */
document.addEventListener("click", function (e) {
  var chip = e.target.closest(".tag-filter .filter-chip[data-tag]");
  if (!chip) return;
  var bar = chip.closest(".tag-filter");
  bar.querySelectorAll(".filter-chip").forEach(function (c) { c.classList.remove("active"); });
  chip.classList.add("active");
  var tag = chip.dataset.tag || "";
  var scope = bar.dataset.filterScope ? document.querySelector(bar.dataset.filterScope) : document;
  if (!scope) scope = document;
  scope.querySelectorAll(".tagged-card").forEach(function (card) {
    var tags = "," + (card.dataset.tags || "") + ",";
    card.style.display = (!tag || tags.indexOf("," + tag + ",") !== -1) ? "" : "none";
  });
});

/* ---------- Second-brain corner popup (visualization only) ---------- */
var makerosBrainData = null;
var makerosBrainRunning = false;

function makerosToggleBrain() {
  var popup = document.getElementById("brain-popup");
  if (!popup) return;
  popup.hidden = !popup.hidden;
  if (!popup.hidden) {
    if (makerosBrainData) {
      makerosStartBrain();
    } else {
      fetch("/wiki/grafos/datos")
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) { makerosBrainData = data; makerosStartBrain(); })
        .catch(function () {
          popup.querySelector(".brain-canvas").innerHTML = "";
        });
    }
  }
}

function makerosBrainColors() {
  var styles = getComputedStyle(document.documentElement);
  function v(name, fallback) {
    var value = styles.getPropertyValue(name).trim();
    return value || fallback;
  }
  return {
    "wiki": v("--brain-wiki", "#29265b"),
    "avisos": v("--brain-avisos", "#b96a00"),
    "projects": v("--brain-projects", "#e42c45"),
    "tasks": v("--brain-tasks", "#3d8a52"),
    "research": v("--brain-research", "#1d4fb8"),
    "inventory": v("--brain-inventory", "#6d6c68"),
    "muted": v("--muted", "#6d6c68"),
    "text": v("--text-title", "#111"),
    "line": v("--border", "#e2e0da")
  };
}

function makerosStartBrain() {
  var canvas = document.getElementById("brain-canvas");
  if (!canvas || !makerosBrainData) return;
  var data = makerosBrainData;
  var ctx = canvas.getContext("2d");
  var nodes = data.nodes, edges = data.edges, byId = {};
  var W = canvas.clientWidth, H = canvas.clientHeight || 440;
  nodes.forEach(function (n, i) {
    var angle = (2 * Math.PI * i) / Math.max(nodes.length, 1);
    n.x = W / 2 + Math.cos(angle) * (W / 3);
    n.y = H / 2 + Math.sin(angle) * (H / 3);
    n.vx = 0; n.vy = 0;
    byId[n.id] = n;
  });
  edges.forEach(function (e) { e.a = byId[e.source]; e.b = byId[e.target]; });

  function resize() {
    if (!document.getElementById("brain-popup") || document.getElementById("brain-popup").hidden) return;
    W = canvas.width = canvas.clientWidth;
    H = canvas.height = canvas.clientHeight || 440;
    nodes.forEach(function (n) {
      n.x = Math.min(Math.max(n.x, 14), W - 14);
      n.y = Math.min(Math.max(n.y, 14), H - 14);
    });
  }

  function step() {
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i + 1; j < nodes.length; j++) {
        var a = nodes[i], b = nodes[j];
        var dx = b.x - a.x, dy = b.y - a.y;
        var d2 = dx * dx + dy * dy || 1;
        var f = 2600 / d2;
        var d = Math.sqrt(d2);
        a.vx -= (dx / d) * f; a.vy -= (dy / d) * f;
        b.vx += (dx / d) * f; b.vy += (dy / d) * f;
      }
    }
    nodes.forEach(function (n) {
      n.vx += (W / 2 - n.x) * 0.003;
      n.vy += (H / 2 - n.y) * 0.003;
    });
    edges.forEach(function (e) {
      if (!e.a || !e.b) return;
      var dx = e.b.x - e.a.x, dy = e.b.y - e.a.y;
      var d = Math.sqrt(dx * dx + dy * dy) || 1;
      var f = (d - 100) * 0.01;
      e.a.vx += (dx / d) * f; e.a.vy += (dy / d) * f;
      e.b.vx -= (dx / d) * f; e.b.vy -= (dy / d) * f;
    });
    nodes.forEach(function (n) {
      n.vx *= 0.85; n.vy *= 0.85;
      n.x += Math.max(-4, Math.min(4, n.vx));
      n.y += Math.max(-4, Math.min(4, n.vy));
      n.x = Math.min(Math.max(n.x, 14), W - 14);
      n.y = Math.min(Math.max(n.y, 14), H - 14);
    });
  }

  function draw() {
    var popup = document.getElementById("brain-popup");
    if (!popup || popup.hidden) { makerosBrainRunning = false; return; }
    step();
    var colors = makerosBrainColors();
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = colors.line;
    ctx.globalAlpha = 0.4;
    edges.forEach(function (e) {
      if (!e.a || !e.b) return;
      ctx.beginPath();
      ctx.moveTo(e.a.x, e.a.y);
      ctx.lineTo(e.b.x, e.b.y);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;
    nodes.forEach(function (n) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, 5, 0, 2 * Math.PI);
      ctx.fillStyle = colors[n.collection] || colors.wiki;
      ctx.fill();
      ctx.font = "11px sans-serif";
      ctx.fillStyle = colors.muted;
      var label = n.title.length > 20 ? n.title.slice(0, 19) + "…" : n.title;
      ctx.fillText(label, n.x + 8, n.y + 3);
    });
    requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener("resize", resize);
  if (!makerosBrainRunning) {
    makerosBrainRunning = true;
    requestAnimationFrame(draw);
  }
}

/* Popup corner-drag resize, remembered between opens. */
document.addEventListener("DOMContentLoaded", function () {
  var popup = document.getElementById("brain-popup");
  var handle = document.getElementById("brain-resize");
  if (!popup || !handle) return;
  try {
    var saved = JSON.parse(localStorage.getItem("makeros-brain-size") || "null");
    if (saved && saved.w && saved.h) {
      popup.style.width = saved.w + "px";
      popup.style.height = saved.h + "px";
    }
  } catch (e) { /* defaults */ }
  handle.addEventListener("mousedown", function (e) {
    e.preventDefault();
    var startX = e.clientX, startY = e.clientY;
    var startW = popup.offsetWidth, startH = popup.offsetHeight;
    function onMove(ev) {
      var w = Math.min(Math.max(startW + (startX - ev.clientX), 420), window.innerWidth - 40);
      var h = Math.min(Math.max(startH + (startY - ev.clientY), 320), window.innerHeight - 120);
      popup.style.width = w + "px";
      popup.style.height = h + "px";
      window.dispatchEvent(new Event("resize"));  // canvas follows
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      try {
        localStorage.setItem("makeros-brain-size", JSON.stringify(
          { w: popup.offsetWidth, h: popup.offsetHeight }
        ));
      } catch (err) { /* private mode */ }
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
});
