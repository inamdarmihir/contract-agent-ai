import React, { useEffect, useRef, useState, useCallback } from 'react'
import './VoiceAgent.css'

/**
 * VoiceAgent
 *
 * Manages the real-time voice session with the xAI Grok voice model.
 *
 * Flow:
 * 1. On mount (or when user clicks "Start"), request an ephemeral token from
 *    the backend `/voice/session` endpoint.
 * 2. Open a WebSocket to the backend proxy `/voice/proxy/{collection_id}` which
 *    forwards traffic to `wss://api.x.ai/v1/realtime`.
 * 3. Capture microphone audio via the Web Audio API and stream PCM16 data to
 *    the voice model.
 * 4. Play back audio deltas returned by the model using the AudioContext.
 * 5. Display a live transcript of the conversation.
 *
 * Props:
 *   collectionId  string  - UUID of the Qdrant contract collection.
 *   apiBase       string  - Base URL for the backend API (e.g. "/api").
 */

const SAMPLE_RATE = 24000      // xAI realtime API requires 24 kHz PCM16
const BUFFER_SIZE = 4096

export default function VoiceAgent({ collectionId, apiBase }) {
  const [status, setStatus] = useState('idle')   // idle | connecting | connected | error
  const [transcript, setTranscript] = useState([]) // [{role, text}]
  const [isMuted, setIsMuted] = useState(false)
  const [error, setError] = useState(null)

  const wsRef = useRef(null)
  const audioCtxRef = useRef(null)
  const sourceNodeRef = useRef(null)
  const processorRef = useRef(null)
  const streamRef = useRef(null)
  const playbackQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const currentAssistantRef = useRef('')

  // ── Audio playback helpers ─────────────────────────────────────────────────

  /** Decode a base64 PCM16 chunk and enqueue it for playback. */
  const enqueueAudio = useCallback((base64Data) => {
    if (!audioCtxRef.current) return
    const binary = atob(base64Data)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

    // Convert PCM16 (Int16) → Float32
    const int16 = new Int16Array(bytes.buffer)
    const float32 = new Float32Array(int16.length)
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768

    const buffer = audioCtxRef.current.createBuffer(1, float32.length, SAMPLE_RATE)
    buffer.copyToChannel(float32, 0)
    playbackQueueRef.current.push(buffer)

    if (!isPlayingRef.current) playNextChunk()
  }, [])

  const playNextChunk = useCallback(() => {
    if (!audioCtxRef.current || playbackQueueRef.current.length === 0) {
      isPlayingRef.current = false
      return
    }
    isPlayingRef.current = true
    const buffer = playbackQueueRef.current.shift()
    const source = audioCtxRef.current.createBufferSource()
    source.buffer = buffer
    source.connect(audioCtxRef.current.destination)
    source.onended = playNextChunk
    source.start()
  }, [])

  // ── WebSocket message handler ──────────────────────────────────────────────

  const handleMessage = useCallback(
    (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return
      }

      switch (msg.type) {
        case 'session.created':
        case 'session.updated':
          setStatus('connected')
          break

        case 'response.audio.delta':
          if (msg.delta) enqueueAudio(msg.delta)
          break

        case 'response.audio_transcript.delta':
          currentAssistantRef.current += msg.delta ?? ''
          break

        case 'response.audio_transcript.done':
          if (currentAssistantRef.current.trim()) {
            setTranscript((prev) => [
              ...prev,
              { role: 'assistant', text: currentAssistantRef.current },
            ])
          }
          currentAssistantRef.current = ''
          break

        case 'conversation.item.input_audio_transcription.completed':
          if (msg.transcript?.trim()) {
            setTranscript((prev) => [
              ...prev,
              { role: 'user', text: msg.transcript },
            ])
          }
          break

        case 'error':
          setError(msg.error?.message ?? 'Unknown voice session error')
          setStatus('error')
          break

        default:
          break
      }
    },
    [enqueueAudio],
  )

  // ── Start voice session ────────────────────────────────────────────────────

  const startSession = useCallback(async () => {
    setError(null)
    setStatus('connecting')

    try {
      // Set up AudioContext
      audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE,
      })

      // Get microphone access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Connect to backend WebSocket proxy
      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const wsHost = apiBase.replace(/^https?:\/\//, '').replace(/^\/api/, '')
      const wsBase = wsHost
        ? `${wsProtocol}://${wsHost}`
        : `${wsProtocol}://${window.location.host}`
      const wsUrl = apiBase.startsWith('http')
        ? `${wsProtocol}://${apiBase.replace(/^https?:\/\//, '')}/voice/proxy/${collectionId}`
        : `${wsProtocol}://${window.location.host}/api/voice/proxy/${collectionId}`

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.addEventListener('open', () => {
        setStatus('connecting') // waiting for session.created event
        startMicCapture(stream, ws)
      })

      ws.addEventListener('message', handleMessage)

      ws.addEventListener('close', () => {
        setStatus('idle')
        stopSession()
      })

      ws.addEventListener('error', () => {
        setError('WebSocket connection failed. Is the backend running?')
        setStatus('error')
        stopSession()
      })
    } catch (e) {
      setError(e.message)
      setStatus('error')
    }
  }, [collectionId, apiBase, handleMessage])

  // ── Microphone capture ─────────────────────────────────────────────────────

  const startMicCapture = useCallback((stream, ws) => {
    const ctx = audioCtxRef.current
    const source = ctx.createMediaStreamSource(stream)
    sourceNodeRef.current = source

    // ScriptProcessor (deprecated but widely supported; replace with AudioWorklet
    // in a production app for better performance).
    const processor = ctx.createScriptProcessor(BUFFER_SIZE, 1, 1)
    processorRef.current = processor

    processor.onaudioprocess = (e) => {
      if (ws.readyState !== WebSocket.OPEN || isMuted) return
      const float32 = e.inputBuffer.getChannelData(0)

      // Resample to 24 kHz if the microphone is at a different rate.
      const resampled = resampleFloat32(float32, ctx.sampleRate, SAMPLE_RATE)

      // Convert Float32 → PCM16
      const int16 = new Int16Array(resampled.length)
      for (let i = 0; i < resampled.length; i++) {
        int16[i] = Math.max(-32768, Math.min(32767, Math.round(resampled[i] * 32767)))
      }

      const base64 = arrayBufferToBase64(int16.buffer)
      ws.send(
        JSON.stringify({ type: 'input_audio_buffer.append', audio: base64 }),
      )
    }

    source.connect(processor)
    processor.connect(ctx.destination)
  }, [isMuted])

  // ── Stop session ───────────────────────────────────────────────────────────

  const stopSession = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect()
      sourceNodeRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close()
      audioCtxRef.current = null
    }
    playbackQueueRef.current = []
    isPlayingRef.current = false
    setStatus('idle')
  }, [])

  // Cleanup on unmount
  useEffect(() => () => stopSession(), [stopSession])

  // ── Render ─────────────────────────────────────────────────────────────────

  const isActive = status === 'connected' || status === 'connecting'

  return (
    <div className="voice-agent">
      <h2 className="voice-title">Voice Assistant</h2>

      {/* Status indicator */}
      <div className={`voice-status voice-status--${status}`}>
        <span className={`status-dot dot--${status}`} />
        {STATUS_LABELS[status]}
      </div>

      {error && (
        <div className="voice-error" role="alert">
          {error}
        </div>
      )}

      {/* Controls */}
      <div className="voice-controls">
        {!isActive ? (
          <button
            className="btn btn-primary voice-btn"
            onClick={startSession}
            disabled={status === 'connecting'}
          >
            🎙️ Start Voice Session
          </button>
        ) : (
          <>
            <button
              className={`btn ${isMuted ? 'btn-primary' : 'btn-ghost'} voice-btn`}
              onClick={() => setIsMuted((m) => !m)}
            >
              {isMuted ? '🔇 Unmute' : '🎤 Mute'}
            </button>
            <button className="btn btn-ghost voice-btn" onClick={stopSession}>
              ⏹ End Session
            </button>
          </>
        )}
      </div>

      {/* Transcript */}
      <div className="transcript">
        {transcript.length === 0 ? (
          <p className="transcript-empty">
            {isActive
              ? 'Listening… ask a question about your contract.'
              : 'Start a voice session to chat with your contract.'}
          </p>
        ) : (
          transcript.map((item, idx) => (
            <div key={idx} className={`turn turn--${item.role}`}>
              <span className="turn-role">{item.role === 'user' ? 'You' : 'Agent'}</span>
              <p className="turn-text">{item.text}</p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_LABELS = {
  idle: 'Not connected',
  connecting: 'Connecting…',
  connected: 'Connected — speak now',
  error: 'Error',
}

/** Naive linear resampler for Float32 audio. */
function resampleFloat32(input, fromRate, toRate) {
  if (fromRate === toRate) return input
  const ratio = fromRate / toRate
  const outputLength = Math.round(input.length / ratio)
  const output = new Float32Array(outputLength)
  for (let i = 0; i < outputLength; i++) {
    const pos = i * ratio
    const idx = Math.floor(pos)
    const frac = pos - idx
    const a = input[idx] ?? 0
    const b = input[idx + 1] ?? 0
    output[i] = a + frac * (b - a)
  }
  return output
}

/** Convert an ArrayBuffer to a base64 string. */
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}
