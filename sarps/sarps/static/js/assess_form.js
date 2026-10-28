// Assessment form helpers. The server re-checks everything; this only saves the student a round trip.
//  1. Show the CGPA box only when "Yes, I have my current CGPA" is chosen.
//  2. Check, as the student types, that counts make sense (submitted <= assigned, and so on).
(function () {
  var form = document.getElementById("assess-form");
  if (!form) return;

  // ---- 1. CGPA box ----
  var cgpaBox = document.getElementById("cgpa-box");
  var cgpaInput = document.getElementById("previous_cgpa");
  var radios = form.querySelectorAll('input[name="has_cgpa"]');
  function syncCgpa() {
    var choice = form.querySelector('input[name="has_cgpa"]:checked');
    var show = !!choice && choice.value === "yes";
    if (cgpaBox) cgpaBox.classList.toggle("is-hidden", !show);
    if (cgpaInput) {
      cgpaInput.disabled = !show;
      if (!show) cgpaInput.value = "";
    }
  }
  radios.forEach(function (radio) { radio.addEventListener("change", syncCgpa); });
  syncCgpa();

  // ---- 2. Live checks on the counts ----
  var submit = form.querySelector('button[type="submit"]');
  var modelOff = submit && submit.hasAttribute("data-model-off");
  function num(id) {
    var el = document.getElementById(id);
    if (!el || el.value.trim() === "") return null;
    var n = Number(el.value);
    return Number.isFinite(n) ? n : null;
  }
  function setLive(id, message) {
    var input = document.getElementById(id);
    if (!input) return false;
    var holder = input.closest(".field");
    var live = holder.querySelector("[data-live]");
    if (message) {
      if (!live) {
        live = document.createElement("p");
        live.className = "error-text";
        live.setAttribute("role", "alert");
        live.setAttribute("data-live", "true");
        holder.appendChild(live);
      }
      live.textContent = message;
    } else if (live) {
      live.remove();
    }
    return !!message;
  }
  function check() {
    var assigned = num("assignments_assigned"), submitted = num("assignments_submitted");
    var done = num("tests_done"), high = num("tests_high"), low = num("tests_low");
    var bad = false;
    bad = setLive("assignments_submitted",
      assigned !== null && submitted !== null && submitted > assigned
        ? "You cannot have submitted more assignments (" + submitted + ") than were assigned (" + assigned + ")." : "") || bad;
    bad = setLive("tests_high",
      done !== null && high !== null && high > done
        ? "This cannot be more than the number of tests or CAs you have done (" + done + ")." : "") || bad;
    var lowMessage = "";
    if (done !== null && low !== null && low > done) {
      lowMessage = "This cannot be more than the number of tests or CAs you have done (" + done + ").";
    } else if (done !== null && high !== null && low !== null && high <= done && high + low > done) {
      lowMessage = "A test cannot be both above 70% and below 50%, so these two cannot add up to more than " + done + ".";
    }
    bad = setLive("tests_low", lowMessage) || bad;
    if (submit && !modelOff) submit.disabled = bad;
  }
  ["assignments_assigned", "assignments_submitted", "tests_done", "tests_high", "tests_low"].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", check);
  });
  check();
})();
