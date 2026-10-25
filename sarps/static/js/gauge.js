// Semicircular probability meter, drawn with Chart.js.
// The exact percentage is always printed as text beside it, so the meter
// never carries meaning on its own.
(function () {
  if (typeof Chart === "undefined") return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Draws a short line at the 50% point (top centre of the arc): the At Risk / Not at Risk boundary.
  var thresholdMark = {
    id: "thresholdMark",
    afterDatasetsDraw: function (chart) {
      var arc = chart.getDatasetMeta(0).data[0];
      if (!arc) return;
      var ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = "#2a2950";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(arc.x, arc.y - arc.outerRadius - 4);
      ctx.lineTo(arc.x, arc.y - arc.innerRadius + 2);
      ctx.stroke();
      ctx.restore();
    }
  };

  document.querySelectorAll(".gauge[data-gauge]").forEach(function (gauge) {
    var value = parseFloat(gauge.dataset.gauge);
    var canvas = gauge.querySelector("canvas");
    if (!canvas || !isFinite(value)) return;
    value = Math.min(100, Math.max(0, value));
    var fill = getComputedStyle(gauge).getPropertyValue("--gauge-fill").trim() || "#5f67b0";

    new Chart(canvas, {
      type: "doughnut",
      data: { datasets: [{ data: [value, 100 - value], backgroundColor: [fill, "#dfe6f3"], borderWidth: 0 }] },
      options: {
        rotation: -90,
        circumference: 180,
        cutout: "72%",
        aspectRatio: 2,
        events: [],
        animation: { duration: reduceMotion ? 0 : 700 },
        plugins: { legend: { display: false }, tooltip: { enabled: false } }
      },
      plugins: [thresholdMark]
    });
  });
})();
