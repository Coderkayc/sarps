// Mobile menu: show/hide the navigation when the menu button is pressed.
(function () {
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;

  function setOpen(open) {
    nav.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  }

  toggle.addEventListener("click", function () {
    setOpen(!nav.classList.contains("is-open"));
  });

  // Close the menu after tapping a link (useful on phones).
  nav.addEventListener("click", function (event) {
    if (event.target.tagName === "A") setOpen(false);
  });
})();

// Tables on phones: label every cell with its column heading so each row can show as a small card.
(function () {
  document.querySelectorAll("table.table").forEach(function (table) {
    var heads = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) {
      return th.textContent.trim();
    });
    table.querySelectorAll("tbody tr").forEach(function (row) {
      Array.prototype.forEach.call(row.children, function (cell, index) {
        if (cell.tagName !== "TD" || cell.hasAttribute("colspan")) return;
        cell.setAttribute("data-label", heads[index] || "");
        var wrapper = document.createElement("span");
        wrapper.className = "cell-value";
        while (cell.firstChild) wrapper.appendChild(cell.firstChild);
        cell.appendChild(wrapper);
      });
    });
  });
})();
