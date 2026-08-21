// Alert-keyword highlighting for Summary text. Rule-based, same spirit as
// the Python classifier (classify.py/exposure.py) -- a curated phrase list,
// not an LLM. Only fires on genuine signal words, deliberately short lists:
// a "Christmas tree" of highlights on every other word defeats the point.
//
// Call highlightKeywords() on text that has ALREADY been through
// escapeHtml() -- it only inserts <strong> tags around matched spans of
// that already-safe text, it never receives or re-escapes raw untrusted
// input. Bold weight only, no color/background -- per user request, plain
// bold reads faster in a dense table than a colored highlight box.

const KEYWORD_GROUPS = [
  {
    cls: "kw-vn",
    phrases: ["socialist republic of vietnam", "vietnamese", "vietnam"],
  },
  {
    cls: "kw-high",
    phrases: [
      "antidumping duty order", "countervailing duty order", "safeguard order",
      "circumvention", "anti-circumvention", "evasion inquiry",
      "transshipment", "final affirmative", "final determination",
      "final results", "final action", "withhold release order",
      "revoked", "rescinded", "rescission", "imposed",
    ],
  },
  {
    cls: "kw-medium",
    phrases: [
      "preliminary determination", "preliminary affirmative", "preliminary negative",
      "preliminary results", "administrative review", "sunset review",
      "changed circumstances review", "new shipper review",
      "investigation initiated", "notice of initiation",
      "scope ruling", "scope inquiry", "entity list", "export control",
      "tariff modification",
    ],
  },
];

const ALL_PHRASES = KEYWORD_GROUPS.flatMap((g) => g.phrases.map((p) => ({ phrase: p, cls: g.cls })))
  .sort((a, b) => b.phrase.length - a.phrase.length);

const CLASS_BY_PHRASE = new Map(ALL_PHRASES.map((p) => [p.phrase, p.cls]));

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const MATCH_RE = new RegExp(
  `\\b(${ALL_PHRASES.map((p) => escapeRegex(p.phrase)).join("|")})\\b`,
  "gi"
);

export function highlightKeywords(escapedText) {
  return escapedText.replace(MATCH_RE, (match) => {
    const cls = CLASS_BY_PHRASE.get(match.toLowerCase());
    return `<strong class="${cls}">${match}</strong>`;
  });
}
