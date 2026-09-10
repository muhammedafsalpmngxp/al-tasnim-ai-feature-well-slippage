// Numbers/percentages/dates get one colour; verbatim database
// content (a recorded cause, an activity name, remarks text...)
// gets another. The term list is never fixed here — it comes from
// `insight.highlight_terms`, built server-side from whatever the
// current well or portfolio JSON actually contains.
const NUMERIC_PARTS = [
  '(\\d{4}-\\d{2}-\\d{2})', // date
  '(\\d+(?:\\.\\d+)?\\s?%)', // percent
  '(\\d+(?:\\.\\d+)?)' // plain number
]

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function buildPattern(terms) {
  // DB terms are tried before the numeric groups, and longest
  // first, so a multi-word term is matched whole rather than a
  // numeric fragment inside it being matched first.
  const termAlternation = (terms || [])
    .filter(Boolean)
    .slice()
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join('|')

  const parts = termAlternation
    ? [`(${termAlternation})`, ...NUMERIC_PARTS]
    : NUMERIC_PARTS

  return new RegExp(parts.join('|'), 'gi')
}

function classify(match, hasTerms) {
  // Group order in the pattern shifts depending on whether a term
  // alternation was prepended — read it back the same way.
  const offset = hasTerms ? 1 : 0

  if (hasTerms && match[1]) return 'term-db'
  if (match[1 + offset]) return 'num-date'
  if (match[2 + offset]) return 'num-percent'
  if (match[3 + offset]) return 'num-value'
  return 'num-value'
}

function highlight(text, terms) {
  const hasTerms = Boolean((terms || []).filter(Boolean).length)
  const pattern = buildPattern(terms)

  const nodes = []
  let lastIndex = 0
  let key = 0
  let match

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }

    nodes.push(
      <span key={key++} className={classify(match, hasTerms)}>
        {match[0]}
      </span>
    )

    lastIndex = match.index + match[0].length

    // A term could theoretically be an empty string after
    // filtering — guard against an infinite loop just in case.
    if (match[0].length === 0) {
      pattern.lastIndex += 1
    }
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes
}

export default function InsightPanel({ title, insight, loading, error }) {
  const summary = insight?.summary

  return (
    <div className="insight">
      <div className="insight-head">
        <span className="insight-title">{title}</span>
        {insight?.model && <span className="insight-model">{insight.model}</span>}
      </div>

      {loading && <p className="muted">Generating summary…</p>}

      {error && <p className="insight-error">{error}</p>}

      {!loading && !error && summary && (
        <p className="insight-paragraph">
          {highlight(summary, insight?.highlight_terms)}
        </p>
      )}
    </div>
  )
}
