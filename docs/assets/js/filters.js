// Filter state + predicate logic. Mirrors app.py's filter semantics exactly:
// each category is AND'd together; within a multiselect category, an event
// matches if ANY selected value is present (OR).

export function createFilterState(meta) {
  return {
    dateStart: meta.date_range.min,
    dateEnd: meta.date_range.max,
    legalBasis: new Set(),
    riskLevel: new Set(),
    vnExposure: new Set(),
    sectors: new Set(),
    stage: new Set(),
    companies: new Set(),
    hideLowConfidence: true,
    sort: "newest",
  };
}

export function applyFilters(events, state) {
  return events.filter((e) => {
    if (state.dateStart && e.date < state.dateStart) return false;
    if (state.dateEnd && e.date > state.dateEnd) return false;
    if (state.legalBasis.size && !e.legal_basis.some((b) => state.legalBasis.has(b))) return false;
    if (state.riskLevel.size && !state.riskLevel.has(e.risk_level)) return false;
    if (state.vnExposure.size && !state.vnExposure.has(e.vn_exposure)) return false;
    if (state.sectors.size && !e.sectors.some((s) => state.sectors.has(s))) return false;
    if (state.stage.size && !state.stage.has(e.stage)) return false;
    if (state.companies.size && !e.companies.some((c) => state.companies.has(c))) return false;
    if (state.hideLowConfidence && e.low_confidence) return false;
    return true;
  });
}

export function sortEvents(events, sort) {
  const sorted = [...events].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  if (sort === "newest") sorted.reverse();
  return sorted;
}
