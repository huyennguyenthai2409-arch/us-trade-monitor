// DOM rendering. Every function takes plain data and writes into a known
// DOM node -- no framework, no virtual DOM, this scale (~4-5k rows) doesn't
// need one.

import { highlightKeywords } from "./highlight.js";

export function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-US", { weekday: "short", day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).toUpperCase();
}

function fmtTimestamp(iso) {
  if (!iso) return "NO DATA YET";
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }).toUpperCase();
  const date = d.toLocaleDateString("en-US", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).toUpperCase();
  const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
  return `${day} · ${date} · ${time} UTC`;
}

export function renderHero(meta) {
  document.getElementById("hero-meta").textContent = `DATA AS OF ${fmtTimestamp(meta.last_run_at)}`;
  document.getElementById("footer-generated").textContent = `Generated ${fmtTimestamp(meta.generated_at)}`;
}

export function renderTopSummary(meta) {
  document.getElementById("ts-kpi-date").textContent = `AS OF ${meta.last_run_date || ""}`;
  document.getElementById("ts-kpi-value").textContent = meta.high_count;
  document.getElementById("ts-kpi-label").textContent = "High-priority alerts";
  document.getElementById("ts-kpi-sub").textContent = `${meta.medium_count} medium · ${meta.direct_vn_count} direct VN exposure`;

  const mixTotal = Math.max(1, meta.high_count + meta.medium_count + meta.low_count);
  document.getElementById("rm-track").innerHTML = `
    <i class="high" style="width:${(meta.high_count / mixTotal) * 100}%"></i>
    <i class="medium" style="width:${(meta.medium_count / mixTotal) * 100}%"></i>
    <i class="low" style="width:${(meta.low_count / mixTotal) * 100}%"></i>`;
  document.getElementById("rm-legend").innerHTML = `
    <span><i class="high"></i>High ${meta.high_count}</span>
    <span><i class="medium"></i>Medium ${meta.medium_count}</span>
    <span><i class="low"></i>Low ${meta.low_count}</span>`;

  const rows = meta.top_legal_basis_high.slice(0, 6);
  const maxCount = Math.max(1, ...rows.map((r) => r.count));
  document.getElementById("contrib-rows").innerHTML = rows
    .map(
      (r) => `
      <div class="contrib-row">
        <div class="c-label">${escapeHtml(r.label)}</div>
        <div class="c-value tnum">${r.count}</div>
        <div class="bar-track"><i style="width:${(r.count / maxCount) * 100}%"></i></div>
        <div class="c-range">of ${meta.high_count}</div>
      </div>`
    )
    .join("");
  // Sum the rows actually shown, not meta.high_count -- an event with more
  // than one legal-basis tag is counted once per tag in top_legal_basis_high,
  // so those two totals aren't guaranteed equal (shown explicitly below
  // rather than presented as a false "=" equation when they diverge).
  const shownSum = rows.reduce((sum, r) => sum + r.count, 0);
  const eqLine =
    shownSum === meta.high_count
      ? `${rows.map((r) => r.count).join(" + ")} = ${shownSum}`
      : `${rows.map((r) => r.count).join(" + ")} = ${shownSum} mentions across ${meta.high_count} alerts`;
  document.getElementById("contrib-eq").textContent = eqLine;

  document.getElementById("ranked-events").innerHTML = meta.top_events
    .map((e) => {
      const dotClass = e.risk_level === "High" ? "tag-risk-high" : e.risk_level === "Medium" ? "tag-risk-medium" : "tag-risk-low";
      const subject = e.sectors.join(", ") || e.countries.join(", ") || "Unspecified";
      // Slice the RAW text first, then escape, then highlight. Slicing the
      // already-escaped string instead can cut an HTML entity in half (e.g.
      // "&amp;" -> "&amp") and also desyncs the ellipsis-length check below
      // from what was actually cut.
      const desc = highlightKeywords(escapeHtml(e.summary.slice(0, 140))) + (e.summary.length > 140 ? "…" : "");
      return `
      <div class="ranked-event">
        <span class="re-dot ${dotClass}" style="background:currentColor;"></span>
        <div class="re-body">
          <span class="re-title">${escapeHtml(e.action)} — ${escapeHtml(subject)} (${escapeHtml(e.countries.join(", ") || "—")})</span>
          <div class="re-desc">${desc}</div>
        </div>
        <div class="re-score tnum">${e.risk_score}</div>
      </div>`;
    })
    .join("");
}

export function renderKpis(filtered) {
  const high = filtered.filter((e) => e.risk_level === "High").length;
  const medium = filtered.filter((e) => e.risk_level === "Medium").length;
  const direct = filtered.filter((e) => e.vn_exposure === "Direct").length;
  document.getElementById("events-count-label").textContent =
    `${filtered.length} shown · ${high} high · ${medium} medium · ${direct} direct VN`;
}

function riskTagClass(level) {
  return level === "High" ? "tag-risk-high" : level === "Medium" ? "tag-risk-medium" : "tag-risk-low";
}
function vnTagClass(exposure) {
  return exposure === "Direct" ? "tag-vn-direct" : exposure === "Indirect" ? "tag-vn-indirect" : "tag-vn-none";
}

export function renderTable(filtered) {
  const tbody = document.getElementById("events-tbody");
  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="12" class="empty-state">No events match the current filters.</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered
    .map(
      (e) => `
    <tr>
      <td class="t-date tnum">${e.date}</td>
      <td>${e.legal_basis.map((b) => `<span class="basis-chip">${escapeHtml(b)}</span>`).join("") || "—"}</td>
      <td>${escapeHtml(e.action)}</td>
      <td><span class="tag ${vnTagClass(e.vn_exposure)}">${escapeHtml(e.vn_exposure)}</span></td>
      <td>${escapeHtml(e.countries.join(", ")) || "—"}</td>
      <td>${escapeHtml(e.sectors.join(", ")) || "—"}</td>
      <td>${escapeHtml(e.stage) || "—"}</td>
      <td class="ta-right t-score tnum">${e.risk_score}</td>
      <td><span class="tag ${riskTagClass(e.risk_level)}">${escapeHtml(e.risk_level)}</span></td>
      <td>${escapeHtml(e.companies.join(", ")) || "—"}</td>
      <td class="t-summary">${highlightKeywords(escapeHtml(e.summary))}</td>
      <td class="t-source"><a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">Open</a></td>
    </tr>`
    )
    .join("");
}

export function renderSectorRankedList(meta) {
  const rows = meta.top_sectors;
  const max = Math.max(1, ...rows.map((r) => r.count));
  document.getElementById("sector-ranked-list").innerHTML = rows
    .map(
      (r) => `
    <div class="ranked-row">
      <div class="rl-label">${escapeHtml(r.sector)}</div>
      <div class="rl-bar"><i style="width:${(r.count / max) * 100}%"></i></div>
      <div class="rl-value tnum">${r.count}</div>
    </div>`
    )
    .join("");
}

export function renderWeeklyChart(meta) {
  const el = document.getElementById("weekly-chart");
  const rows = meta.weekly_counts;
  if (!rows.length) {
    el.innerHTML = `<div class="empty-state">No data yet.</div>`;
    return;
  }
  const W = 900, H = 260, padL = 40, padR = 20, padT = 20, padB = 30;
  const values = rows.map((r) => r.count);
  const min = Math.min(...values), max = Math.max(...values);
  const x = (i) => padL + (i / Math.max(1, rows.length - 1)) * (W - padL - padR);
  const y = (v) => H - padB - ((v - min) / Math.max(1, max - min)) * (H - padT - padB);

  const gridLines = [min, (min + max) / 2, max]
    .map((v) => `<line class="chart-grid" x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" /><text x="4" y="${y(v) + 4}">${Math.round(v)}</text>`)
    .join("");

  const points = rows.map((r, i) => [x(i), y(r.count)]);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const dots = points.map(([px, py]) => `<circle class="chart-dot" cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5" />`).join("");

  const peakIdx = values.indexOf(max);
  const peak = rows[peakIdx];
  const annotation = `<text class="chart-annotation" x="${x(peakIdx).toFixed(1)}" y="${(y(peak.count) - 10).toFixed(1)}" text-anchor="middle">${peak.count} · ${peak.week_start}</text>`;

  el.innerHTML = `<svg class="chart-svg" viewBox="0 0 ${W} ${H}" width="100%" height="${H}">${gridLines}<path class="chart-line" d="${path}" />${dots}${annotation}</svg>`;
}

export function renderDigestSelect(digestsIndex) {
  const select = document.getElementById("digest-select");
  select.innerHTML = digestsIndex.map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join("");
}

const BAND_LABEL = { HIGH: "🔴 HIGH", MEDIUM: "🟡 MEDIUM", LOW: "🟢 LOW" };

export function renderDigest(digest) {
  const el = document.getElementById("digest-body");
  if (!digest || !digest.events.length) {
    el.innerHTML = `<p class="muted">Fetched ${digest ? digest.fetched : 0} documents, ${digest ? digest.new_documents : 0} new, 0 High-priority alerts. No new documents matched this run.</p>`;
    return;
  }
  const bands = ["HIGH", "MEDIUM", "LOW"];
  const byBand = Object.fromEntries(bands.map((b) => [b, digest.events.filter((e) => e.band === b)]));
  el.innerHTML =
    `<p class="muted">Fetched ${digest.fetched} documents (${digest.start_date} to ${digest.end_date}), ${digest.new_documents} new, ${digest.new_alerts} High-priority alerts.</p>` +
    bands
      .filter((b) => byBand[b].length)
      .map(
        (b) => `
      <h4 style="margin-top:20px;">${BAND_LABEL[b]}</h4>
      ${byBand[b]
        .map(
          (e) => `
        <div style="padding:10px 0; border-top:1px solid var(--rule-2);">
          <strong>${escapeHtml(e.title)}</strong><br/>
          <span class="muted">${escapeHtml(e.agency)} · ${escapeHtml(e.legal_basis.join(", ") || "n/a")} · ${escapeHtml(e.doc_type)} · Risk ${e.risk_score} (${escapeHtml(e.risk_level)})</span><br/>
          <a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">Source →</a>
        </div>`
        )
        .join("")}`
      )
      .join("");
}

export function renderCompanies(companies) {
  document.getElementById("companies-tbody").innerHTML = companies
    .map(
      (c) => `
    <tr>
      <td>${escapeHtml(c.ticker)}</td>
      <td>${escapeHtml(c.company_name)}</td>
      <td>${escapeHtml(c.sector)}</td>
      <td>${escapeHtml(c.subsector)}</td>
    </tr>`
    )
    .join("");
}
