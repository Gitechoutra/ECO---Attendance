import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api } from '../../api/client'
import { useToast } from '../../context/ToastContext'
import { Button, Checkbox, Modal } from '../../components/ui'
import FaceCapture from './FaceCapture'

export const CONSENT_TEXT = [
  'ECHOUTRA IT SOLUTIONS will create a mathematical face template (not a photograph) to verify your identity when you mark attendance.',
  'The template is encrypted, used only for attendance verification, and never shared outside the company.',
  'You can revoke consent at any time from your profile; the template is then deleted immediately.',
  'Templates of former employees are deleted automatically after the configured retention period.',
  'If you do not consent, you can mark attendance through manual requests approved by HR.',
]

export default function FaceEnrollModal({ open, onClose, employee, onEnrolled, self = false }) {
  const toast = useToast()
  const [consent, setConsent] = useState(false)
  const [stage, setStage] = useState('consent')
  const close = () => { setStage('consent'); setConsent(false); onClose() }
  return (
    <Modal open={open} onClose={close} title={self ? 'Set up face check-in' : `Enroll face — ${employee?.full_name || ''}`} size="md"
      footer={stage === 'consent' ? <><Button variant="secondary" onClick={close}>Cancel</Button><Button disabled={!consent} onClick={() => setStage('capture')}>Continue to camera</Button></> : null}>
      {stage === 'consent' ? (
        <div className="space-y-4">
          <div className="flex gap-3 rounded-xl border border-line bg-surface-2 p-4">
            <ShieldCheck className="h-5 w-5 shrink-0 text-brand-ink" />
            <ul className="space-y-2 text-[13px] text-ink-2">{CONSENT_TEXT.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
          <Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)}
            label={self ? 'I have read this notice and consent to face verification for attendance' : 'The employee has read this notice and gives explicit consent'}
            description={self ? 'Your consent is recorded with time and version. You can revoke it anytime from My profile.' : 'Consent is recorded with time, version and the enrolling administrator.'} />
        </div>
      ) : (
        <FaceCapture
          purpose="enroll"
          employeeId={employee.id}
          submitLabel={self ? 'Start live capture' : 'Start enrollment'}
          submit={async (p) => (await api.post('/attendance/face/enroll', { ...p, employee_id: employee.id, consent_confirmed: true })).data}
          onDone={() => { toast.success(self ? 'Face check-in is ready' : 'Face profile enrolled', self ? 'You can now check in with the camera.' : undefined); onEnrolled?.(); close() }}
        />
      )}
    </Modal>
  )
}
