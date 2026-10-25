// Assessment form: when "I have no previous CGPA" is ticked, the CGPA box is switched off.
(function () {
  var box = document.getElementById("cgpa_unavailable");
  var input = document.getElementById("previous_cgpa");
  if (!box || !input) return;

  function sync() { input.disabled = box.checked; }
  box.addEventListener("change", function () {
    if (box.checked) input.value = "";
    sync();
  });
  sync();
})();
