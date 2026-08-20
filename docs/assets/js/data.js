// Fetches the JSON exported by export_site_data.py and exposes it as an
// in-memory store. Relative paths only -- this site is served under a GH
// Pages project subpath (/us-trade-monitor/), not the domain root.

async function fetchJson(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return res.json();
}

export async function loadData() {
  const [events, meta, companies, digestsIndex] = await Promise.all([
    fetchJson("./data/events.json"),
    fetchJson("./data/meta.json"),
    fetchJson("./data/companies.json"),
    fetchJson("./data/digests_index.json"),
  ]);
  return { events, meta, companies, digestsIndex };
}

export async function loadDigest(date) {
  return fetchJson(`./data/digests/${date}.json`);
}
