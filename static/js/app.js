const LEVEL_COLORS = {
  AD: "#4caf50",
  A: "#ffc107",
  B: "#ff6d00",
  C: "#ff2f7d",
};

const LEVEL_LABELS = {
  AD: "AD (Logro destacado)",
  A: "A (Logro esperado)",
  B: "B (En proceso)",
  C: "C (En inicio)",
};

const ORDINAL_LEVEL_LABELS = {
  1: "C - En inicio",
  2: "B - En proceso",
  3: "A - Logro esperado",
  4: "AD - Logro destacado",
};

document.addEventListener("DOMContentLoaded", () => {
  const cicloSelect = document.querySelector(".js-ciclo-select");
  const areaSelect = document.querySelector(".js-area-select");
  const competenciaSelect = document.querySelector(".js-competencia-select");

  const resetCompetencias = (message = "Selecciona primero un area") => {
    if (!competenciaSelect) return;
    competenciaSelect.innerHTML = `<option value="">${message}</option>`;
    competenciaSelect.disabled = true;
  };

  if (cicloSelect && areaSelect && competenciaSelect) {
    cicloSelect.addEventListener("change", async () => {
      areaSelect.innerHTML = '<option value="">Cargando areas...</option>';
      areaSelect.disabled = true;
      resetCompetencias();
      if (!cicloSelect.value) {
        areaSelect.innerHTML = '<option value="">Selecciona primero un ciclo</option>';
        return;
      }
      const response = await fetch(`/api/areas?ciclo=${encodeURIComponent(cicloSelect.value)}`);
      const data = await response.json();
      areaSelect.innerHTML = '<option value="">Selecciona un area</option>';
      data.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `${item.nombre} (${item.ciclo})`;
        areaSelect.appendChild(option);
      });
      areaSelect.disabled = data.length === 0;
    });
  }

  if (areaSelect && competenciaSelect) {
    areaSelect.addEventListener("change", async () => {
      competenciaSelect.innerHTML = '<option value="">Cargando...</option>';
      competenciaSelect.disabled = true;
      if (!areaSelect.value) {
        competenciaSelect.innerHTML = '<option value="">Selecciona primero un area</option>';
        return;
      }
      const cycleQuery = cicloSelect && cicloSelect.value
        ? `?ciclo=${encodeURIComponent(cicloSelect.value)}`
        : "";
      const response = await fetch(`/api/competencias/${areaSelect.value}${cycleQuery}`);
      const data = await response.json();
      competenciaSelect.innerHTML = '<option value="">Selecciona una competencia</option>';
      data.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.ciclo ? `${item.nombre} (${item.ciclo})` : item.nombre;
        competenciaSelect.appendChild(option);
      });
      competenciaSelect.disabled = data.length === 0;
    });
  }
});

function chartData(stats) {
  const labels = stats.criterios.map((item, index) => `${index + 1}. ${item.descripcion}`);
  const byLevelPercent = {};
  const byLevelCount = {};
  stats.levels.forEach((level) => {
    byLevelPercent[level] = stats.criterios.map((item) => item.percentages[level]);
    byLevelCount[level] = stats.criterios.map((item) => item.counts[level]);
  });
  return { labels, byLevelPercent, byLevelCount };
}

function lineChartData(stats) {
  const shortLabels = stats.criterios.map((_, index) => `C${index + 1}`);
  const fullLabels = stats.criterios.map((item, index) => ({
    key: `C${index + 1}`,
    criterio: item.descripcion,
    capacidad: item.capacidad_nombre,
  }));
  return { shortLabels, fullLabels };
}

function renderLineCriteriaLegend(criteria) {
  const legend = document.getElementById("lineCriteriaLegend");
  if (!legend) return;
  legend.innerHTML = criteria
    .map((item) => `<span><strong>${item.key}:</strong> ${item.criterio}</span>`)
    .join("");
}

function renderStudentCriteriaLegend(criteria) {
  const legend = document.getElementById("studentCriteriaLegend");
  if (!legend) return;
  legend.innerHTML = criteria
    .map((item) => `<span><strong>${item.key}:</strong> ${item.criterio}</span>`)
    .join("");
}

function renderStudentProfileChart(stats) {
  const chartCanvas = document.getElementById("studentProfileChart");
  const select = document.getElementById("studentProfileSelect");
  const title = document.getElementById("studentProfileTitle");
  const profiles = stats && stats.individual_profiles;
  if (!window.Chart || !chartCanvas || !select || !profiles || !profiles.students.length) return;

  const labels = profiles.criteria.map((item) => item.key);
  renderStudentCriteriaLegend(profiles.criteria);

  const findStudent = () => (
    profiles.students.find((student) => String(student.id) === String(select.value))
    || profiles.students[0]
  );

  const tooltipTitle = (items) => {
    const criterion = profiles.criteria[items[0].dataIndex];
    return `${criterion.key} - ${criterion.criterio}`;
  };

  const tooltipLabel = (context) => {
    const student = findStudent();
    const level = student.levels[context.dataIndex];
    if (!level || !level.nivel) return "Nivel obtenido: Sin evaluacion";
    return `Nivel obtenido: ${level.nivel} (${level.label})`;
  };

  const initialStudent = findStudent();
  if (title) title.textContent = `Perfil de logro - ${initialStudent.nombre}`;

  const chart = new Chart(chartCanvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Nivel obtenido",
        data: initialStudent.values,
        borderColor: "#214f9c",
        backgroundColor: "rgba(33, 79, 156, 0.14)",
        pointBackgroundColor: "#214f9c",
        pointBorderColor: "#214f9c",
        spanGaps: false,
        tension: 0.25,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        intersect: false,
        mode: "index",
      },
      scales: {
        x: {
          ticks: {
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
          },
          grid: { display: false },
        },
        y: {
          min: 1,
          max: 4,
          ticks: {
            stepSize: 1,
            callback: (value) => ORDINAL_LEVEL_LABELS[value] || value,
          },
        },
      },
      elements: {
        point: {
          radius: 4,
          hoverRadius: 6,
        },
        line: {
          borderWidth: 2.5,
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: tooltipTitle,
            label: tooltipLabel,
          },
        },
      },
    },
  });

  select.addEventListener("change", () => {
    const student = findStudent();
    chart.data.datasets[0].data = student.values;
    if (title) title.textContent = `Perfil de logro - ${student.nombre}`;
    chart.update();
  });
}

function renderResultCharts(stats, printMode = false) {
  if (!window.Chart || !stats) return;
  Chart.defaults.font.family = "'Inter', 'Segoe UI', Arial, sans-serif";
  Chart.defaults.color = "#17213b";

  const { labels, byLevelPercent } = chartData(stats);
  const datasets = stats.levels.map((level) => ({
    label: LEVEL_LABELS[level],
    data: byLevelPercent[level],
    backgroundColor: LEVEL_COLORS[level],
    borderColor: LEVEL_COLORS[level],
    borderWidth: printMode ? 1 : 2,
    tension: 0.25,
  }));

  const stacked = document.getElementById("stackedChart");
  if (stacked) {
    new Chart(stacked, {
      type: "bar",
      data: { labels, datasets },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true, max: 100, ticks: { callback: (value) => `${value}%` } },
          y: { stacked: true },
        },
        plugins: { legend: { position: printMode ? "right" : "bottom" } },
      },
    });
  }

  const bar = document.getElementById("barChart");
  if (bar) {
    new Chart(bar, {
      type: "bar",
      data: {
        labels: stats.levels.map((level) => LEVEL_LABELS[level]),
        datasets: [{
          label: "Porcentaje general",
          data: stats.levels.map((level) => stats.general_percentages[level]),
          backgroundColor: stats.levels.map((level) => LEVEL_COLORS[level]),
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, max: 100, ticks: { callback: (value) => `${value}%` } } },
        plugins: { legend: { display: false } },
      },
    });
  }

  const pie = document.getElementById("pieChart");
  if (pie) {
    new Chart(pie, {
      type: "pie",
      data: {
        labels: stats.levels.map((level) => LEVEL_LABELS[level]),
        datasets: [{
          data: stats.levels.map((level) => stats.general_counts[level]),
          backgroundColor: stats.levels.map((level) => LEVEL_COLORS[level]),
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "right" } },
      },
    });
  }

  const line = document.getElementById("lineChart");
  if (line) {
    const { shortLabels, fullLabels } = lineChartData(stats);
    renderLineCriteriaLegend(fullLabels);
    new Chart(line, {
      type: "line",
      data: { labels: shortLabels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {
          intersect: false,
          mode: "index",
        },
        scales: {
          x: {
            ticks: {
              autoSkip: false,
              maxRotation: 0,
              minRotation: 0,
            },
            grid: {
              display: false,
            },
          },
          y: {
            beginAtZero: true,
            min: 0,
            max: 100,
            ticks: {
              stepSize: 20,
              callback: (value) => `${value}%`,
            },
          },
        },
        elements: {
          point: {
            radius: printMode ? 2.5 : 3.5,
            hoverRadius: 5,
          },
          line: {
            borderWidth: printMode ? 2 : 2.5,
          },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              title: (items) => {
                const item = fullLabels[items[0].dataIndex];
                return `${item.key}: ${item.criterio}`;
              },
              afterTitle: (items) => {
                const item = fullLabels[items[0].dataIndex];
                return item.capacidad ? `Capacidad: ${item.capacidad}` : "";
              },
              label: (context) => `${context.dataset.label}: ${context.parsed.y}%`,
            },
          },
        },
      },
    });
  }

  renderStudentProfileChart(stats);
}
