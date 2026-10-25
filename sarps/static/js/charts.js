// History line chart: probability of Not at Risk over time, with the 50% line.
// The same numbers are in the table on the page, so the chart is a convenience.
(function () {
  if (typeof Chart === "undefined") return;
  var canvas = document.getElementById("history-chart");
  var source = document.getElementById("history-data");
  if (!canvas || !source) return;

  var data = JSON.parse(source.textContent);
  var ok = "#2a9d82", risk = "#d6456b";
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  new Chart(canvas, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        {
          label: "Probability of Not at Risk (%)",
          data: data.values,
          borderColor: "#5f67b0",
          tension: 0.25,
          pointRadius: 6,
          // Colour AND shape: circle = Not at Risk, triangle = At Risk.
          pointBackgroundColor: data.values.map(function (v) { return v > 50 ? ok : risk; }),
          pointStyle: data.values.map(function (v) { return v > 50 ? "circle" : "triangle"; })
        },
        {
          label: "50% threshold",
          data: data.labels.map(function () { return 50; }),
          borderColor: "#596179",
          borderDash: [6, 6],
          borderWidth: 1.5,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: reduceMotion ? 0 : 600 },
      scales: {
        y: { min: 0, max: 100, title: { display: true, text: "Probability of Not at Risk (%)" } }
      },
      plugins: { legend: { position: "bottom" } }
    }
  });
})();
