import { loadData, loadDigest } from "./data.js";
import { createFilterState, applyFilters, sortEvents } from "./filters.js";
import {
  escapeHtml,
  renderHero,
  renderTopSummary,
  renderKpis,
  renderTable,
  renderSectorRankedList,
  renderWeeklyChart,
  renderDigestSelect,
  renderDigest,
  renderCompanies,
} from "./render.js";

const DISPLAY_HEADERS = [
  "Date", "Legal Basis", "Action", "VN Exposure", "Country", "Sector",
  "Stage", "Risk Score", "Risk", "Companies", "Summary", "Source",
];

function toCsv(rows) {
  const lines = [DISPLAY_HEADERS.join(",")];
  for (const e of rows) {
    const fields = [
      e.date,
      e.legal_basis.join("; "),
      e.action,
      e.vn_exposure,
      e.countries.join(", "),
      e.sectors.join("; "),
      e.stage,
      e.risk_score,
      e.risk_level,
      e.companies.join(", "),
      e.summary,
      e.source,
    ];
    lines.push(fields.map((f) => `"${String(f).replace(/"/g, '""')}"`).join(","));
  }
  return lines.join("\r\n");
}

function downloadCsv(rows) {
  const blob = new Blob(["﻿" + toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "us_trade_events.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

function buildMultiSelect({ key, label, options, state, onChange }) {
  const field = document.createElement("div");
  field.className = "filter-field";
  const selected = state[key];

  const renderValue = () =>
    selected.size ? `${selected.size} selected` : "All";

  field.innerHTML = `
    <span class="filter-label">${escapeHtml(label)}</span>
    <div class="filter-select">
      <button type="button" class="fs-btn">
        <span class="fs-value ${selected.size ? "" : "placeholder"}">${renderValue()}</span>
        <span class="fs-chevron"></span>
      </button>
      <div class="filter-menu">
        ${options
          .map(
            (opt) => `
          <div class="filter-option" data-value="${escapeHtml(opt.value)}">
            <span class="opt-check"></span>
            <span>${escapeHtml(opt.label)}</span>
          </div>`
          )
          .join("")}
      </div>
    </div>`;

  const selectEl = field.querySelector(".filter-select");
  const btn = field.querySelector(".fs-btn");
  const valueEl = field.querySelector(".fs-value");

  btn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    document.querySelectorAll(".filter-select.open").forEach((el) => {
      if (el !== selectEl) el.classList.remove("open");
    });
    selectEl.classList.toggle("open");
  });

  field.querySelectorAll(".filter-option").forEach((optEl) => {
    optEl.addEventListener("click", () => {
      const value = optEl.dataset.value;
      if (selected.has(value)) {
        selected.delete(value);
        optEl.classList.remove("active");
      } else {
        selected.add(value);
        optEl.classList.add("active");
      }
      valueEl.textContent = renderValue();
      valueEl.classList.toggle("placeholder", !selected.size);
      onChange();
    });
  });

  return field;
}

function buildDateField({ label, value, min, max, onChange }) {
  const field = document.createElement("div");
  field.className = "filter-field";
  field.innerHTML = `
    <span class="filter-label">${escapeHtml(label)}</span>
    <input type="date" class="filter-date" value="${escapeHtml(value)}" min="${escapeHtml(min)}" max="${escapeHtml(max)}" />`;
  field.querySelector("input").addEventListener("change", (ev) => onChange(ev.target.value));
  return field;
}

function buildFilterBar(meta, state, onChange) {
  const bar = document.getElementById("filter-bar");
  bar.innerHTML = "";

  bar.appendChild(
    buildDateField({
      label: "From",
      value: state.dateStart,
      min: meta.date_range.min,
      max: meta.date_range.max,
      onChange: (v) => {
        state.dateStart = v;
        onChange();
      },
    })
  );
  bar.appendChild(
    buildDateField({
      label: "To",
      value: state.dateEnd,
      min: meta.date_range.min,
      max: meta.date_range.max,
      onChange: (v) => {
        state.dateEnd = v;
        onChange();
      },
    })
  );

  bar.appendChild(
    buildMultiSelect({
      key: "legalBasis",
      label: "Legal basis",
      options: meta.facets.legal_basis.map((b) => ({ value: b.key, label: b.label })),
      state,
      onChange,
    })
  );
  bar.appendChild(
    buildMultiSelect({
      key: "riskLevel",
      label: "Risk level",
      options: ["High", "Medium", "Low"].map((v) => ({ value: v, label: v })),
      state,
      onChange,
    })
  );
  bar.appendChild(
    buildMultiSelect({
      key: "vnExposure",
      label: "Vietnam exposure",
      options: ["Direct", "Indirect", "None"].map((v) => ({ value: v, label: v })),
      state,
      onChange,
    })
  );
  bar.appendChild(
    buildMultiSelect({
      key: "sectors",
      label: "Sector",
      options: meta.facets.sectors.map((v) => ({ value: v, label: v })),
      state,
      onChange,
    })
  );
  bar.appendChild(
    buildMultiSelect({
      key: "stage",
      label: "Stage",
      options: meta.facets.stages.map((v) => ({ value: v, label: v })),
      state,
      onChange,
    })
  );
  bar.appendChild(
    buildMultiSelect({
      key: "companies",
      label: "Company",
      options: meta.facets.companies.map((v) => ({ value: v, label: v })),
      state,
      onChange,
    })
  );
}

async function main() {
  const { events, meta, companies, digestsIndex } = await loadData();
  const state = createFilterState(meta);

  let currentFiltered = [];

  function refresh() {
    const filtered = applyFilters(events, state);
    currentFiltered = sortEvents(filtered, state.sort);
    renderKpis(currentFiltered);
    renderTable(currentFiltered);
  }

  buildFilterBar(meta, state, refresh);

  document.getElementById("hide-low-confidence").addEventListener("change", (ev) => {
    state.hideLowConfidence = ev.target.checked;
    refresh();
  });

  document.getElementById("sort-toggle").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-sort]");
    if (!btn) return;
    state.sort = btn.dataset.sort;
    document.querySelectorAll("#sort-toggle button").forEach((b) => b.classList.toggle("active", b === btn));
    refresh();
  });

  document.addEventListener("click", () => {
    document.querySelectorAll(".filter-select.open").forEach((el) => el.classList.remove("open"));
  });

  document.getElementById("download-csv").addEventListener("click", () => downloadCsv(currentFiltered));
  document.getElementById("download-csv-2").addEventListener("click", () => downloadCsv(currentFiltered));

  renderHero(meta);
  renderTopSummary(meta);
  renderSectorRankedList(meta);
  renderWeeklyChart(meta);
  renderCompanies(companies);

  if (digestsIndex.length) {
    renderDigestSelect(digestsIndex);
    const select = document.getElementById("digest-select");
    const showDigest = async (date) => renderDigest(await loadDigest(date));
    select.addEventListener("change", (ev) => showDigest(ev.target.value));
    await showDigest(digestsIndex[0]);
  }

  refresh();
}

main().catch((err) => {
  console.error(err);
  document.querySelector(".shell").insertAdjacentHTML(
    "afterbegin",
    `<div style="padding:24px; background:#FEE; color:#900;">Failed to load data: ${escapeHtml(err.message)}</div>`
  );
});
