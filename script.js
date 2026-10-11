const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("en-US");

const VARIANTS = {
  essay: { label: "Essay", host: "essay.leoasaservice.com" },
  jay: { label: "Jay / conversation", host: "jay.leoasaservice.com" },
  sales: { label: "Focused sales page", host: "www.leoasaservice.com" },
  quai: { label: "Quai trust path", host: "quai.leoasaservice.com" }
};

const SOURCES = ["YouTube", "LinkedIn", "X", "Direct", "Other"];

function sum(rows, key) {
  return rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);
}

function fmtRate(numerator, denominator) {
  if (!denominator) return "—";
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function render(data) {
  const experiment = data.experiment || {};
  const leaves = Array.isArray(data.leafNodes) ? data.leafNodes : [];
  const metrics = data.metrics || {};
  const metricVariants = metrics.variants || {};
  const variantRows = Object.keys(VARIANTS).map((id) => {
    const rows = leaves.filter((row) => row.variant === id);
    return {
      id,
      ...VARIANTS[id],
      traffic: Number(metricVariants[id]?.traffic ?? sum(rows, "traffic")),
      cta: Number(metricVariants[id]?.ctaClicks ?? sum(rows, "ctaClicks")),
      bookings: Number(metricVariants[id]?.bookings ?? sum(rows, "bookings")),
      paid: Number(metricVariants[id]?.paidConversions ?? sum(rows, "paidConversions")),
      revenue: Number(metricVariants[id]?.revenue ?? sum(rows, "revenue"))
    };
  });

  const totals = {
    traffic: Number(metrics.totals?.traffic ?? sum(variantRows, "traffic")),
    cta: Number(metrics.totals?.ctaClicks ?? sum(variantRows, "cta")),
    bookings: Number(metrics.totals?.bookings ?? sum(variantRows, "bookings")),
    paid: Number(metrics.totals?.paidConversions ?? sum(variantRows, "paid")),
    revenue: Number(metrics.totals?.revenue ?? sum(variantRows, "revenue"))
  };

  document.title = `${experiment.name || "LAAS Experiment"} — Scoreboard`;
  document.querySelector("#experiment-name").textContent = experiment.name || "Three-way landing page experiment";
  document.querySelector("#experiment-copy").textContent = experiment.description || "Traffic from the network enters one of three termination points. The scoreboard follows it to money.";
  document.querySelector("#experiment-window").textContent = `${experiment.durationDays || 14}-day window`;
  document.querySelector("#last-updated").textContent = `Data updated ${data.updatedAt || "—"}`;
  document.querySelector("#data-source-note").textContent = `Source: ${data.source || "scoreboard data"}`;
  const attribution = metrics.attribution || {};
  const unallocated = metrics.unallocated || {};
  const unallocatedTotal = Object.values(unallocated).reduce((total, value) => total + (Number(value) || 0), 0);
  const unallocatedHosts = Object.entries(unallocated).map(([host, traffic]) => `${host}: ${number.format(Number(traffic) || 0)}`).join(" · ");
  document.querySelector("#attribution-note").textContent = `Attribution evidence: ${attribution.exact || 0} exact · ${attribution.fuzzy || 0} fuzzy bucket · ${attribution.ambiguous || 0} ambiguous · ${attribution.unattributed || 0} unattributed · ${number.format(unallocatedTotal)} unmatched hostname traffic${unallocatedHosts ? ` (${unallocatedHosts})` : ""}`;

  document.querySelector("#total-traffic").textContent = number.format(totals.traffic);
  document.querySelector("#total-cta").textContent = number.format(totals.cta);
  document.querySelector("#total-bookings").textContent = number.format(totals.bookings);
  document.querySelector("#total-conversions").textContent = number.format(totals.paid);
  document.querySelector("#total-revenue").textContent = money.format(totals.revenue);

  const minimum = Number(experiment.minimumRevenue) || 10000;
  const maximum = Number(experiment.maximumRevenue) || 100000;
  const gaugePercent = Math.min(100, Math.max(0, (totals.revenue / maximum) * 100));
  document.querySelector("#revenue-gauge-fill").style.width = `${gaugePercent}%`;
  document.querySelector("#revenue-gauge-label").textContent = `${money.format(totals.revenue)} / ${money.format(minimum)} minimum`;

  const status = document.querySelector("#experiment-status");
  const start = experiment.startAt ? new Date(experiment.startAt) : null;
  const durationMs = (Number(experiment.durationDays) || 14) * 24 * 60 * 60 * 1000;
  if (!start || Number.isNaN(start.getTime())) {
    status.textContent = "Not started";
    document.querySelector("#countdown").textContent = "Experiment not started";
  } else {
    const end = new Date(start.getTime() + durationMs);
    const remaining = end.getTime() - Date.now();
    const days = Math.max(0, Math.floor(remaining / 86400000));
    const hours = Math.max(0, Math.floor((remaining % 86400000) / 3600000));
    status.textContent = remaining > 0 ? "Running" : "Complete";
    document.querySelector("#countdown").textContent = remaining > 0 ? `${days}d ${hours}h remaining` : "Experiment window complete";
  }

  document.querySelector("#variant-rows").innerHTML = variantRows.map((row) => `
    <tr>
      <td><div class="variant-name"><strong>${row.label}</strong><span>${row.host}</span></div></td>
      <td>${number.format(row.traffic)}</td>
      <td>${number.format(row.cta)} <span class="muted">(${fmtRate(row.cta, row.traffic)})</span></td>
      <td>${number.format(row.bookings)}</td>
      <td>${number.format(row.paid)}</td>
      <td><strong>${money.format(row.revenue)}</strong></td>
      <td class="${row.paid ? "good" : ""}">${fmtRate(row.paid, row.traffic)}</td>
    </tr>`).join("");

  const sourceTotals = metrics.sources ? Object.entries(metrics.sources).map(([source, values]) => ({ source, ...values })) : SOURCES.map((source) => {
    const rows = leaves.filter((row) => (row.source || "Other") === source);
    return { source, traffic: sum(rows, "traffic"), paid: sum(rows, "paidConversions"), revenue: sum(rows, "revenue") };
  }).filter((row) => row.traffic || row.paid || row.revenue);
  document.querySelector("#source-rows").innerHTML = sourceTotals.length ? sourceTotals.map((row) => `
    <tr><td><strong>${row.source}</strong></td><td>${number.format(row.traffic)}</td><td>${number.format(row.paid)}</td><td>${money.format(row.revenue)}</td></tr>`).join("") : '<tr><td colspan="4" class="empty">No source observations yet.</td></tr>';

  document.querySelector("#leaf-list").innerHTML = leaves.length ? leaves.map((row) => `
    <article class="leaf">
      <div class="leaf-top"><span class="leaf-title">${row.title || "Untitled leaf node"}</span><span>${row.variant || "—"}</span></div>
      <div class="leaf-meta">${row.source || "Other"} · ${row.kind || "content"} · ${row.publishedAt || "date unknown"}</div>
      <div class="leaf-result"><span>${number.format(Number(row.traffic) || 0)} visits</span><span>${number.format(Number(row.paidConversions) || 0)} paid</span><span>${money.format(Number(row.revenue) || 0)}</span></div>
    </article>`).join("") : '<div class="empty">No leaf nodes entered yet.</div>';
}

fetch("data/scoreboard.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Scoreboard data returned ${response.status}`);
    return response.json();
  })
  .then(render)
  .catch((error) => {
    document.querySelector("#experiment-status").textContent = "Data unavailable";
    document.querySelector("#experiment-copy").textContent = error.message;
  });
