"""Permission catalogue and default role grants.

Permissions are enforced on the server through `require_permissions` in app/api/deps.py.
Admins can edit role grants and add or revoke individual permissions per user.
"""

SUPER_ADMIN = "super_admin"
HR_ADMIN = "hr_admin"
PROJECT_MANAGER = "project_manager"
EMPLOYEE = "employee"

ROLES = {
    SUPER_ADMIN: ("Super Admin / CEO", "Complete company-wide access."),
    HR_ADMIN: ("HR / Admin", "People operations: employees, attendance, leave, recruitment, payroll, documents."),
    PROJECT_MANAGER: ("Project Manager", "Assigned projects, tasks, team members and related clients."),
    EMPLOYEE: ("Employee", "Own profile, attendance, leave, tasks, payslips and announcements."),
}

# code -> (module, description)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "dashboard.company": ("Dashboard", "View company-wide dashboard statistics"),
    "employees.view_all": ("Employees", "View all employee profiles"),
    "employees.manage": ("Employees", "Create, edit and deactivate employees"),
    "employees.view_sensitive": ("Employees", "View bank, tax and personal identifiers"),
    "departments.manage": ("Employees", "Manage departments and designations"),
    "attendance.view_all": ("Attendance", "View attendance of all employees"),
    "attendance.manage": ("Attendance", "Manual attendance and correction approvals"),
    "attendance.enroll_face": ("Attendance", "Enroll and remove employee face profiles"),
    "leave.view_all": ("Leave", "View all leave requests and balances"),
    "leave.approve": ("Leave", "Approve or reject leave requests"),
    "leave.configure": ("Leave", "Manage leave types, balances and holidays"),
    "projects.view_all": ("Projects", "View all projects"),
    "projects.manage": ("Projects", "Create and manage projects"),
    "tasks.manage_all": ("Tasks", "Manage tasks in any project"),
    "clients.view": ("Clients", "View client records"),
    "clients.manage": ("Clients", "Create and edit clients"),
    "email.use": ("Email", "Connect authorized mailboxes and use email"),
    "email.view_shared": ("Email", "View shared company mailboxes"),
    "recruitment.view": ("Recruitment", "View openings and candidates"),
    "recruitment.manage": ("Recruitment", "Manage openings, candidates and interviews"),
    "offers.manage": ("Offer Letters", "Draft and send offer letters"),
    "offers.approve": ("Offer Letters", "Approve offer letters"),
    "payroll.view": ("Payroll", "View payroll of all employees"),
    "payroll.manage": ("Payroll", "Configure salaries and process payroll"),
    "expenses.view_all": ("Expenses", "View all expense claims"),
    "expenses.approve": ("Expenses", "Approve or reject expense claims"),
    "expenses.reimburse": ("Expenses", "Record reimbursements"),
    "announcements.manage": ("Communication", "Publish announcements"),
    "meetings.manage": ("Communication", "Schedule company meetings"),
    "reports.view": ("Reports", "View operational reports"),
    "reports.hr": ("Reports", "View HR & attendance reports"),
    "reports.finance": ("Reports", "View payroll and expense reports"),
    "ai.use": ("AI Assistant", "Use the AI company assistant"),
    "admin.users": ("Administration", "Manage user accounts"),
    "admin.roles": ("Administration", "Manage roles and permissions"),
    "admin.settings": ("Administration", "Manage company and system settings"),
    "admin.audit": ("Administration", "View audit logs"),
    "admin.backup": ("Administration", "Create database backups"),
}

ALL = set(PERMISSIONS)

DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    SUPER_ADMIN: ALL,
    HR_ADMIN: {
        "dashboard.company", "employees.view_all", "employees.manage", "employees.view_sensitive",
        "departments.manage", "attendance.view_all", "attendance.manage", "attendance.enroll_face",
        "leave.view_all", "leave.approve", "leave.configure", "projects.view_all", "clients.view",
        "email.use", "recruitment.view", "recruitment.manage", "offers.manage", "payroll.view",
        "payroll.manage", "expenses.view_all", "expenses.approve", "expenses.reimburse",
        "announcements.manage", "meetings.manage", "reports.view", "reports.hr", "reports.finance",
        "ai.use", "admin.users", "admin.audit",
    },
    PROJECT_MANAGER: {
        "clients.view", "email.use", "recruitment.view", "meetings.manage", "reports.view", "ai.use",
    },
    EMPLOYEE: {"ai.use"},
}
