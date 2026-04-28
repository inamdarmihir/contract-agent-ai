import React from 'react'
import './ClauseViewer.css'

/**
 * ClauseViewer
 *
 * Displays the full details of a selected contract clause:
 *   - Original text
 *   - Plain English explanation
 *   - Risk level + reason
 *   - Metadata (page number, section title, clause type)
 *
 * Props:
 *   clause   object   - Clause payload from the Qdrant collection.
 *   onClose  () => void  - Callback to dismiss the viewer.
 */
export default function ClauseViewer({ clause, onClose }) {
  if (!clause) return null

  return (
    <div className="clause-viewer" role="dialog" aria-label="Clause details">
      {/* Header */}
      <div className="clause-header">
        <div className="clause-meta">
          <span className={`risk-badge risk-${clause.risk_level}`}>
            {clause.risk_level} risk
          </span>
          {clause.clause_type && (
            <span className="clause-type-tag">{clause.clause_type}</span>
          )}
          {clause.page_number > 0 && (
            <span className="page-ref">Page {clause.page_number}</span>
          )}
        </div>
        <button className="close-btn" onClick={onClose} aria-label="Close">✕</button>
      </div>

      {/* Section title */}
      {clause.section_title && (
        <h3 className="section-label">{clause.section_title}</h3>
      )}

      {/* Risk reason */}
      {clause.risk_level !== 'low' && clause.risk_reason && (
        <div className={`risk-alert risk-alert--${clause.risk_level}`}>
          <span className="alert-icon">
            {clause.risk_level === 'high' ? '🚨' : '⚠️'}
          </span>
          <p>{clause.risk_reason}</p>
        </div>
      )}

      {/* Plain English summary */}
      {clause.plain_english && (
        <section className="clause-section">
          <h4 className="clause-section-title">Plain English</h4>
          <p className="clause-plain">{clause.plain_english}</p>
        </section>
      )}

      {/* Original text */}
      <section className="clause-section">
        <h4 className="clause-section-title">Original Contract Text</h4>
        <blockquote className="clause-original">{clause.text}</blockquote>
      </section>
    </div>
  )
}
