import React, { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import './RiskDashboard.css'

/**
 * RiskDashboard
 *
 * Displays a visual breakdown of the contract after ingestion:
 *  - Overall risk score (high / medium / low counts)
 *  - Clause-type breakdown bar chart
 *  - Top 5 flagged high-risk clauses
 *  - Page map highlighting pages with high-risk content
 *
 * Props:
 *   analysis        object   - Risk analysis data from the API.
 *   onClauseSelect  (clause) => void  - Callback when user clicks a flagged clause.
 */
export default function RiskDashboard({ analysis, onClauseSelect }) {
  if (!analysis) return null

  const { total_chunks, high, medium, low, top_flagged } = analysis

  const riskPercent = useMemo(() => {
    if (!total_chunks) return { high: 0, medium: 0, low: 0 }
    return {
      high: Math.round((high / total_chunks) * 100),
      medium: Math.round((medium / total_chunks) * 100),
      low: Math.round((low / total_chunks) * 100),
    }
  }, [total_chunks, high, medium, low])

  // Derive clause-type counts from top_flagged for the bar chart.
  const clauseTypeCounts = useMemo(() => {
    const counts = {}
    ;(top_flagged || []).forEach((c) => {
      const t = c.clause_type || 'other'
      counts[t] = (counts[t] || 0) + 1
    })
    return Object.entries(counts).map(([type, count]) => ({ type, count }))
  }, [top_flagged])

  return (
    <div className="dashboard">
      <h2 className="dashboard-title">Risk Dashboard</h2>

      {/* ── Overall risk score ─────────────────────────────────────────── */}
      <section className="section">
        <h3 className="section-title">Overall Risk</h3>
        <div className="risk-pills">
          <RiskPill level="high" count={high} pct={riskPercent.high} />
          <RiskPill level="medium" count={medium} pct={riskPercent.medium} />
          <RiskPill level="low" count={low} pct={riskPercent.low} />
        </div>
        <p className="total-chunks">{total_chunks} total clauses analysed</p>
      </section>

      {/* ── Clause type bar chart ──────────────────────────────────────── */}
      {clauseTypeCounts.length > 0 && (
        <section className="section">
          <h3 className="section-title">Clause Types (flagged)</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={clauseTypeCounts} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="type"
                tick={{ fill: '#94a3b8', fontSize: 12 }}
                width={100}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155' }}
                cursor={{ fill: 'rgba(99,102,241,0.1)' }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {clauseTypeCounts.map((entry) => (
                  <Cell
                    key={entry.type}
                    fill={clauseTypeColor(entry.type)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>
      )}

      {/* ── Top flagged clauses ────────────────────────────────────────── */}
      {top_flagged && top_flagged.length > 0 && (
        <section className="section">
          <h3 className="section-title">⚠️ Top Flagged Clauses</h3>
          <div className="flagged-list">
            {top_flagged.map((clause) => (
              <button
                key={clause.id}
                className={`flagged-card risk-${clause.risk_level}`}
                onClick={() => onClauseSelect(clause)}
                title="Click to view clause details"
              >
                <div className="flagged-header">
                  <span className={`risk-badge risk-${clause.risk_level}`}>
                    {clause.risk_level}
                  </span>
                  <span className="clause-type-tag">{clause.clause_type}</span>
                  <span className="page-ref">p.{clause.page_number}</span>
                </div>
                <p className="flagged-reason">{clause.risk_reason}</p>
                <p className="flagged-plain">{clause.plain_english}</p>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

/** Small risk summary pill component. */
function RiskPill({ level, count, pct }) {
  return (
    <div className={`risk-pill risk-pill--${level}`}>
      <span className="pill-count">{count}</span>
      <span className="pill-label">{level}</span>
      <span className="pill-pct">{pct}%</span>
    </div>
  )
}

/** Return a chart colour for a given clause type. */
function clauseTypeColor(type) {
  const map = {
    liability: '#ef4444',
    termination: '#f59e0b',
    payment: '#22c55e',
    IP: '#6366f1',
    confidentiality: '#8b5cf6',
    'auto-renewal': '#ec4899',
    indemnification: '#f97316',
    other: '#64748b',
  }
  return map[type] ?? '#64748b'
}
