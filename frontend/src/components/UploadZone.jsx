import React, { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import './UploadZone.css'

/**
 * UploadZone
 *
 * Drag-and-drop PDF upload area.  Calls `onUpload(file)` when the user
 * drops or selects a valid PDF file.
 *
 * Props:
 *   onUpload  (File) => void   - Callback invoked with the selected File object.
 */
export default function UploadZone({ onUpload }) {
  const onDrop = useCallback(
    (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        onUpload(acceptedFiles[0])
      }
    },
    [onUpload],
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: false,
    maxSize: 50 * 1024 * 1024, // 50 MB
  })

  return (
    <div className="upload-page">
      <div className="upload-hero">
        <h1>Voice Contract Analyzer</h1>
        <p className="subtitle">
          Upload any PDF contract. The agent will pre-analyse every clause for risk,
          then let you ask questions <em>by voice</em> — no typing required.
        </p>
      </div>

      <div
        {...getRootProps()}
        className={`dropzone ${isDragActive ? 'active' : ''} ${isDragReject ? 'reject' : ''}`}
      >
        <input {...getInputProps()} />
        <div className="dropzone-icon">📄</div>
        {isDragReject ? (
          <p className="dropzone-text reject-text">Only PDF files are accepted</p>
        ) : isDragActive ? (
          <p className="dropzone-text">Drop the contract here…</p>
        ) : (
          <>
            <p className="dropzone-text">Drag &amp; drop your PDF contract here</p>
            <p className="dropzone-hint">or click to select a file · max 50 MB</p>
          </>
        )}
      </div>

      <div className="features-grid">
        {FEATURES.map((f) => (
          <div key={f.title} className="feature-card">
            <span className="feature-icon">{f.icon}</span>
            <div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const FEATURES = [
  {
    icon: '🔍',
    title: 'Pre-analysed risk',
    desc: 'Every clause is scored high / medium / low before you say a word.',
  },
  {
    icon: '🎙️',
    title: 'Voice-first',
    desc: 'Ask questions naturally. No typing, no forms.',
  },
  {
    icon: '🔒',
    title: 'Self-hostable',
    desc: 'Sensitive contracts never leave your infrastructure.',
  },
  {
    icon: '⚡',
    title: 'Hybrid search',
    desc: 'Dense embeddings + BM42 keyword match for precise retrieval.',
  },
]
