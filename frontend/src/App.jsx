import React, { useState, useCallback } from 'react'
import UploadZone from './components/UploadZone.jsx'
import RiskDashboard from './components/RiskDashboard.jsx'
import VoiceAgent from './components/VoiceAgent.jsx'
import ClauseViewer from './components/ClauseViewer.jsx'
import './App.css'

/**
 * Root application component.
 *
 * State machine:
 *   idle       → uploading → processing → ready
 *
 * - idle:       Show the upload zone.
 * - uploading:  PDF is being sent to the backend.
 * - processing: Risk analysis is running in the background; poll the API.
 * - ready:      Show the risk dashboard, voice agent, and clause viewer.
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export default function App() {
  const [phase, setPhase] = useState('idle')      // 'idle' | 'uploading' | 'processing' | 'ready'
  const [collectionId, setCollectionId] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [selectedClause, setSelectedClause] = useState(null)
  const [error, setError] = useState(null)

  /** Called by UploadZone when the user drops / selects a PDF. */
  const handleUpload = useCallback(async (file) => {
    setError(null)
    setPhase('uploading')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail ?? 'Upload failed')
      }
      const data = await res.json()
      setCollectionId(data.collection_id)
      setPhase('processing')
      pollAnalysis(data.collection_id)
    } catch (e) {
      setError(e.message)
      setPhase('idle')
    }
  }, [])

  /** Poll the analysis endpoint until it completes. */
  const pollAnalysis = useCallback(async (cid) => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/contracts/${cid}/analysis`)
        const data = await res.json()
        if (data.status === 'complete') {
          setAnalysis(data.data)
          setPhase('ready')
        } else if (data.status === 'error') {
          setError(data.message ?? 'Risk analysis failed')
          setPhase('idle')
        } else {
          // Still processing — try again in 2 seconds.
          setTimeout(poll, 2000)
        }
      } catch (e) {
        setError(e.message)
        setPhase('idle')
      }
    }
    setTimeout(poll, 2000)
  }, [])

  /** Reset the app to the initial state. */
  const handleReset = () => {
    setPhase('idle')
    setCollectionId(null)
    setAnalysis(null)
    setSelectedClause(null)
    setError(null)
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-icon">⚖️</span>
            <span className="logo-text">Contract Voice Agent</span>
          </div>
          {phase !== 'idle' && (
            <button className="btn btn-ghost" onClick={handleReset}>
              ← Upload new contract
            </button>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="app-main">
        {error && (
          <div className="error-banner" role="alert">
            <strong>Error:</strong> {error}
            <button className="close-btn" onClick={() => setError(null)}>✕</button>
          </div>
        )}

        {phase === 'idle' && (
          <UploadZone onUpload={handleUpload} />
        )}

        {phase === 'uploading' && (
          <div className="status-card">
            <div className="spinner" />
            <p>Uploading contract…</p>
          </div>
        )}

        {phase === 'processing' && (
          <div className="status-card">
            <div className="spinner" />
            <p>Analysing contract clauses…</p>
            <p className="muted">This may take a minute for large contracts.</p>
          </div>
        )}

        {phase === 'ready' && collectionId && (
          <div className="workspace">
            {/* Left column: dashboard + clause viewer */}
            <div className="left-panel">
              <RiskDashboard
                analysis={analysis}
                onClauseSelect={setSelectedClause}
              />
              {selectedClause && (
                <ClauseViewer
                  clause={selectedClause}
                  onClose={() => setSelectedClause(null)}
                />
              )}
            </div>

            {/* Right column: voice agent */}
            <div className="right-panel">
              <VoiceAgent
                collectionId={collectionId}
                apiBase={API_BASE}
              />
            </div>
          </div>
        )}
      </main>

      <footer className="app-footer">
        <p>
          Open source · Self-hostable · MIT license ·{' '}
          <a
            href="https://github.com/inamdarmihir/contract-agent-ai"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>
        </p>
      </footer>
    </div>
  )
}
