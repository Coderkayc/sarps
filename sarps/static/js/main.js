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
