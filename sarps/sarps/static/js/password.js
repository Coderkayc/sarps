// Password fields: show/hide button and the live requirements checklist.
// The rules here only guide the person while typing; the server checks them again.
(function () {
  document.querySelectorAll(".password-toggle").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("data-toggle-for"));
    if (!input) return;
    button.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.setAttribute("aria-pressed", String(show));
    });
  });

  document.querySelectorAll("[data-rules-for]").forEach(function (list) {
    var input = document.getElementById(list.getAttribute("data-rules-for"));
    if (!input) return;
    var minimum = parseInt(list.getAttribute("data-min"), 10) || 8;
    var tests = {
      length: function (p) { return p.length >= minimum; },
      upper: function (p) { return /[A-Z]/.test(p); },
      digit: function (p) { return /[0-9]/.test(p); },
      special: function (p) { return /[^A-Za-z0-9]/.test(p); }
    };
    function update() {
      var value = input.value;
      list.classList.toggle("is-active", value.length > 0);
      list.querySelectorAll("li").forEach(function (item) {
        var ok = tests[item.getAttribute("data-rule")](value);
        item.classList.toggle("is-ok", ok);
      });
    }
    input.addEventListener("input", update);
    update();
  });
})();
