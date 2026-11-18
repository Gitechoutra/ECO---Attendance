import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ShieldOff } from 'lucide-react'
import { useAuth } from './context/AuthContext'
import AppShell from './components/layout/AppShell'
import { EmptyState, Spinner } from './components/ui'
import PwaPrompt from './components/layout/PwaPrompt'

const LoginPage = lazy(() => import('./features/auth/LoginPage'))
const ChangePasswordPage = lazy(() => import('./features/auth/ChangePasswordPage'))
const OfferResponsePage = lazy(() => import('./features/offers/OfferResponsePage'))
const DashboardPage = lazy(() => import('./features/dashboard/DashboardPage'))
const ProfilePage = lazy(() => import('./features/profile/ProfilePage'))
const NotificationsPage = lazy(() => import('./features/notifications/NotificationsPage'))
const EmployeesPage = lazy(() => import('./features/employees/EmployeesPage'))
const EmployeeDetailPage = lazy(() => import('./features/employees/EmployeeDetailPage'))
const OrganizationPage = lazy(() => import('./features/employees/OrganizationPage'))
const AttendancePage = lazy(() => import('./features/attendance/AttendancePage'))
const LeavePage = lazy(() => import('./features/leave/LeavePage'))
const ProjectsPage = lazy(() => import('./features/projects/ProjectsPage'))
const ProjectDetailPage = lazy(() => import('./features/projects/ProjectDetailPage'))
const TasksPage = lazy(() => import('./features/tasks/TasksPage'))
const ClientsPage = lazy(() => import('./features/clients/ClientsPage'))
const ClientDetailPage = lazy(() => import('./features/clients/ClientDetailPage'))
const EmailPage = lazy(() => import('./features/email/EmailPage'))
const RecruitmentPage = lazy(() => import('./features/recruitment/RecruitmentPage'))
const CandidateDetailPage = lazy(() => import('./features/recruitment/CandidateDetailPage'))
const OffersPage = lazy(() => import('./features/offers/OffersPage'))
const OfferDetailPage = lazy(() => import('./features/offers/OfferDetailPage'))
const PayrollPage = lazy(() => import('./features/payroll/PayrollPage'))
const PayrollRunPage = lazy(() => import('./features/payroll/PayrollRunPage'))
const ExpensesPage = lazy(() => import('./features/expenses/ExpensesPage'))
const CommunicationPage = lazy(() => import('./features/communication/CommunicationPage'))
const ReportsPage = lazy(() => import('./features/reports/ReportsPage'))
const AssistantPage = lazy(() => import('./features/ai/AssistantPage'))
const UsersPage = lazy(() => import('./features/admin/UsersPage'))
const AuditPage = lazy(() => import('./features/admin/AuditPage'))
const SettingsPage = lazy(() => import('./features/admin/SettingsPage'))

function RequireAuth({ children }) {
  const { status, user } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <FullScreenLoader />
  if (status !== 'authenticated') return <Navigate to="/login" replace state={{ from: location }} />
  if (user?.must_change_password && location.pathname !== '/change-password') return <Navigate to="/change-password" replace />
  return children
}

/** Hides pages a user cannot use. The API enforces the same permissions server-side. */
function Guard({ any, children }) {
  const { canAny } = useAuth()
  if (any && !canAny(...any)) {
    return <EmptyState icon={ShieldOff} title="You don’t have access to this page" description="Ask an administrator if you need this permission." />
  }
  return children
}

function FullScreenLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-night">
      <img src="/echoutra-mark.png" alt="" className="h-12 w-auto animate-pulse" />
    </div>
  )
}

export default function App() {
  const { status } = useAuth()
  return (
    <>
      <Suspense fallback={status === 'authenticated' ? <Spinner className="min-h-[50vh]" /> : <FullScreenLoader />}>
        <Routes>
          <Route path="/login" element={status === 'authenticated' ? <Navigate to="/" replace /> : <LoginPage />} />
          <Route path="/offer/respond/:token" element={<OfferResponsePage />} />
          <Route path="/change-password" element={<RequireAuth><ChangePasswordPage /></RequireAuth>} />
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route index element={<DashboardPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="notifications" element={<NotificationsPage />} />
            <Route path="employees" element={<Guard any={['employees.view_all']}><EmployeesPage /></Guard>} />
            <Route path="employees/:id" element={<EmployeeDetailPage />} />
            <Route path="attendance/*" element={<AttendancePage />} />
            <Route path="leave/*" element={<LeavePage />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="projects/:id" element={<ProjectDetailPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="tasks/:taskId" element={<TasksPage />} />
            <Route path="clients" element={<Guard any={['clients.view', 'clients.manage']}><ClientsPage /></Guard>} />
            <Route path="clients/:id" element={<Guard any={['clients.view', 'clients.manage']}><ClientDetailPage /></Guard>} />
            <Route path="email" element={<Guard any={['email.use']}><EmailPage /></Guard>} />
            <Route path="recruitment" element={<Guard any={['recruitment.view']}><RecruitmentPage /></Guard>} />
            <Route path="recruitment/candidates/:id" element={<Guard any={['recruitment.view']}><CandidateDetailPage /></Guard>} />
            <Route path="offers" element={<Guard any={['offers.manage', 'offers.approve']}><OffersPage /></Guard>} />
            <Route path="offers/:id" element={<Guard any={['offers.manage', 'offers.approve']}><OfferDetailPage /></Guard>} />
            <Route path="payroll" element={<PayrollPage />} />
            <Route path="payroll/runs/:id" element={<Guard any={['payroll.view']}><PayrollRunPage /></Guard>} />
            <Route path="expenses" element={<ExpensesPage />} />
            <Route path="communication" element={<CommunicationPage />} />
            <Route path="reports" element={<Guard any={['reports.view', 'reports.hr', 'reports.finance']}><ReportsPage /></Guard>} />
            <Route path="assistant" element={<Guard any={['ai.use']}><AssistantPage /></Guard>} />
            <Route path="admin/organization" element={<Guard any={['departments.manage']}><OrganizationPage /></Guard>} />
            <Route path="admin/users" element={<Guard any={['admin.users', 'admin.roles']}><UsersPage /></Guard>} />
            <Route path="admin/audit" element={<Guard any={['admin.audit']}><AuditPage /></Guard>} />
            <Route path="admin/settings" element={<Guard any={['admin.settings']}><SettingsPage /></Guard>} />
            <Route path="*" element={<EmptyState title="Page not found" description="The page you’re looking for doesn’t exist or was moved." />} />
          </Route>
        </Routes>
      </Suspense>
      <PwaPrompt />
    </>
  )
}
