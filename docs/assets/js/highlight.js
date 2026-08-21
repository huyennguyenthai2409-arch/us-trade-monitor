// Alert-keyword highlighting for Summary text. Rule-based, same spirit as
// the Python classifier (classify.py/exposure.py) -- a curated phrase list,
// not an LLM. Only fires on genuine signal words, deliberately short lists:
// a "Christmas tree" of highlights on every other word defeats the point.
//
// Call highlightKeywords() on text that has ALREADY been through
// escapeHtml() -- it only inserts <mark> tags around matched spans of that
// already-safe text, it never receives or re-escapes raw untrusted input.

const KEYWORD_GROUPS = [
  {
    cls: "kw-vn",
    phrases: ["socialist republic of vietnam", "vietnamese", "vietnam"],
  },
  {
    cls: "kw-high",
    phrases: [
      "antidumping duty order", "countervailing duty order", "circumvention",
      "transshipment", "final affirmative", "final determination",
      "final results", "revoked", "imposed",
    ],
  },
  {
    cls: "kw-medium",
    phrases: [
      "preliminary determination", "preliminary affirmative",
      "administrative review", "sunset review", "investigation initiated",
      "notice of initiation",
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
    return `<mark class="${cls}">${match}</mark>`;
  });
}
