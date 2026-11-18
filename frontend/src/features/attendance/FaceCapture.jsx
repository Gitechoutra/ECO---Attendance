import { useCallback, useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { ArrowLeft, ArrowRight, Camera, CheckCircle2, Loader2, RefreshCw, ScanFace, ShieldCheck, VideoOff } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import { Button } from '../../components/ui'

const STEP_MS = 2000
const FRAME_EVERY = 340
const ICON = { center: ScanFace, left: ArrowLeft, right: ArrowRight }

/**
 * Live camera capture with server-issued challenge–response liveness.
 * Only frames grabbed from the live <video> stream are sent; there is no file upload path.
 *
 * props.purpose: check_in | check_out | enroll
 * props.submit(payload) => Promise   payload = { nonce, frames, timestamps }
 */
export default function FaceCapture({ purpose, employeeId, submit, onDone, onFallback, submitLabel = 'Verify' }) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const [phase, setPhase] = useState('starting') // starting | ready | capturing | verifying | success | error | denied
  const [instruction, setInstruction] = useState('')
  const [step, setStep] = useState(null)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)

  const stop = () => streamRef.current?.getTracks().forEach((t) => t.stop())

  const start = useCallback(async () => {
    setPhase('starting')
    setMessage('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setPhase('denied')
      setMessage('This browser cannot access a camera. Use a recent version of Chrome, Edge or Safari over HTTPS.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } }, audio: false })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setPhase('ready')
    } catch (e) {
      setPhase('denied')
      setMessage(e?.name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access in your browser settings and try again.'
        : 'No camera was found or it is in use by another app.')
    }
  }, [])

  useEffect(() => { start(); return stop }, [start])

  const grab = () => {
    const v = videoRef.current
    const c = canvasRef.current
    const w = 480
    const h = Math.round((v.videoHeight / v.videoWidth) * w) || 360
    c.width = w
    c.height = h
    c.getContext('2d').drawImage(v, 0, 0, w, h) // raw (un-mirrored) frame
    return c.toDataURL('image/jpeg', 0.78)
  }

  const run = async () => {
    setMessage('')
    let ch
    try {
      ch = (await api.post('/attendance/challenge', { purpose, employee_id: employeeId })).data
    } catch (e) {
      setPhase('error'); setMessage(errorMessage(e)); return
    }
    setPhase('capturing')
    const frames = []
    const timestamps = []
    const total = ch.steps.length * STEP_MS
    const t0 = performance.now()
    await new Promise((resolve) => {
      let lastGrab = 0
      const tick = () => {
        const el = performance.now() - t0
        const idx = Math.min(Math.floor(el / STEP_MS), ch.steps.length - 1)
        setStep(ch.steps[idx])
        setInstruction(ch.instructions[idx])
        setProgress(Math.min(el / total, 1))
        if (el - lastGrab >= FRAME_EVERY && frames.length < 24) {
          lastGrab = el
          frames.push(grab())
          timestamps.push(Math.round(el))
        }
        if (el < total) requestAnimationFrame(tick)
        else resolve()
      }
      requestAnimationFrame(tick)
    })
    setPhase('verifying')
    setStep(null)
    try {
      const res = await submit({ nonce: ch.nonce, frames: frames.slice(0, 24), timestamps: timestamps.slice(0, 24) })
      setResult(res)
      setPhase('success')
      stop()
      setTimeout(() => onDone?.(res), 1100)
    } catch (e) {
      setPhase('error')
      setMessage(errorMessage(e, 'Verification failed'))
    }
  }

  const StepIcon = step ? ICON[step] : ScanFace
  return (
    <div>
      <div className="relative mx-auto aspect-[4/3] w-full max-w-md overflow-hidden rounded-2xl bg-night">
        <video ref={videoRef} playsInline muted className={clsx('h-full w-full -scale-x-100 object-cover transition-opacity', phase === 'denied' && 'opacity-0')} />
        <canvas ref={canvasRef} className="hidden" />
        {/* oval guide */}
        {['ready', 'capturing'].includes(phase) && (
          <svg viewBox="0 0 400 300" className="pointer-events-none absolute inset-0 h-full w-full">
            <defs><mask id="oval"><rect width="400" height="300" fill="white" /><ellipse cx="200" cy="142" rx="88" ry="112" fill="black" /></mask></defs>
            <rect width="400" height="300" fill="rgba(5,11,15,.45)" mask="url(#oval)" />
            <ellipse cx="200" cy="142" rx="88" ry="112" fill="none" stroke={phase === 'capturing' ? '#00BEA3' : 'rgba(255,255,255,.7)'} strokeWidth="2.5" strokeDasharray={phase === 'capturing' ? '0' : '6 6'} />
          </svg>
        )}
        {phase === 'capturing' && (
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-night/90 to-transparent px-5 pb-4 pt-10 text-center text-white">
            <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-brand text-[#03211D]"><StepIcon className="h-5 w-5" /></div>
            <p className="text-[15px] font-semibold">{instruction}</p>
            <div className="mx-auto mt-3 h-1 w-40 overflow-hidden rounded-full bg-white/20"><div className="h-full bg-brand transition-[width] duration-100" style={{ width: `${progress * 100}%` }} /></div>
          </div>
        )}
        {(phase === 'starting' || phase === 'verifying') && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-night/70 text-white">
            <Loader2 className="h-7 w-7 animate-spin text-brand" />
            <p className="text-sm">{phase === 'starting' ? 'Starting camera…' : 'Verifying identity and liveness…'}</p>
          </div>
        )}
        {phase === 'success' && (
          <div className="absolute inset-0 flex animate-fade-in flex-col items-center justify-center gap-2 bg-night/80 text-white">
            <CheckCircle2 className="h-12 w-12 text-brand" />
            <p className="text-base font-semibold">{purpose === 'enroll' ? 'Face profile enrolled' : 'Verified'}</p>
            {result?.verification && <p className="num text-xs text-[#A9BAC4]">Match score {(result.verification.score * 100).toFixed(0)}%</p>}
          </div>
        )}
        {phase === 'denied' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-white">
            <VideoOff className="h-8 w-8 text-[#A9BAC4]" />
            <p className="text-sm text-[#C8D5DC]">{message}</p>
          </div>
        )}
      </div>

      <div className="mx-auto mt-4 max-w-md">
        {phase === 'ready' && (
          <>
            <ul className="mb-4 space-y-1.5 text-[13px] text-muted">
              <li className="flex gap-2"><Camera className="mt-0.5 h-3.5 w-3.5 shrink-0" />Face the camera in good light, with your face inside the oval.</li>
              <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />You’ll be asked to turn your head. This live check prevents photo spoofing.</li>
            </ul>
            <Button className="w-full" size="lg" icon={ScanFace} onClick={run}>{submitLabel}</Button>
          </>
        )}
        {phase === 'error' && (
          <div className="space-y-3">
            <div className="rounded-lg border border-danger/25 bg-danger-soft px-3 py-2.5 text-[13px] text-danger">{message}</div>
            <Button className="w-full" icon={RefreshCw} onClick={() => setPhase('ready')}>Try again</Button>
          </div>
        )}
        {phase === 'denied' && <Button className="w-full" variant="secondary" icon={RefreshCw} onClick={start}>Retry camera</Button>}
        {onFallback && ['error', 'denied', 'ready'].includes(phase) && (
          <button onClick={onFallback} className="mt-3 w-full text-center text-[13px] font-medium text-brand-ink hover:underline">Camera not working? Request manual attendance</button>
        )}
      </div>
    </div>
  )
}
