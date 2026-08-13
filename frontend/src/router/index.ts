import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/monitoring',
    name: 'monitoring',
    component: () => import('@/views/MonitoringView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/servers',
    name: 'servers',
    component: () => import('@/views/ServersView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/applications',
    name: 'applications',
    component: () => import('@/views/ApplicationsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/applications/:id',
    name: 'application-detail',
    component: () => import('@/views/ApplicationDetailView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/operations',
    name: 'operations',
    component: () => import('@/views/OperationsView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/domains',
    name: 'domains',
    component: () => import('@/views/DomainsView.vue'),
    meta: { requiresAuth: true, permission: 'domains:read' },
  },
  {
    path: '/databases',
    name: 'databases',
    component: () => import('@/views/DatabasesView.vue'),
    meta: { requiresAuth: true, permission: 'databases:read' },
  },
  {
    path: '/databases/studio',
    name: 'database-studio',
    component: () => import('@/views/DatabaseStudioView.vue'),
    meta: { requiresAuth: true, permission: 'databases:read' },
  },
  {
    path: '/ssl',
    name: 'ssl',
    component: () => import('@/views/SslView.vue'),
    meta: { requiresAuth: true, permission: 'ssl:read' },
  },
  {
    path: '/admin/mail',
    name: 'mail-admin',
    component: () => import('@/views/MailView.vue'),
    meta: { requiresAuth: true, permission: 'mail:read' },
  },
  {
    path: '/files/upload',
    name: 'files-upload',
    component: () => import('@/views/FileUploadView.vue'),
    meta: { requiresAuth: true, permission: 'files:write' },
  },
  {
    path: '/files/edit',
    name: 'file-editor',
    component: () => import('@/views/FileEditorView.vue'),
    meta: { requiresAuth: true, permission: 'files:read' },
  },
  {
    path: '/files',
    name: 'files',
    component: () => import('@/views/FilesView.vue'),
    meta: { requiresAuth: true, permission: 'files:read' },
  },
  {
    path: '/terminal/full',
    name: 'terminal-full',
    component: () => import('@/views/TerminalFullscreenView.vue'),
    meta: { requiresAuth: true, permission: 'terminal:execute' },
  },
  {
    path: '/terminal',
    name: 'terminal',
    component: () => import('@/views/TerminalView.vue'),
    meta: { requiresAuth: true, permission: 'terminal:execute' },
  },
  {
    path: '/security',
    name: 'security',
    component: () => import('@/views/SecurityView.vue'),
    meta: { requiresAuth: true, permission: 'system:admin' },
  },
  {
    path: '/servers',
    name: 'servers',
    component: () => import('@/views/ServersView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { requiresAuth: true },
  },
  // IFNOTUS customer portal (product layer)
  {
    path: '/portal',
    name: 'portal-plans',
    component: () => import('@/views/portal/PortalPlansView.vue'),
    meta: { guestOnly: false },
  },
  {
    path: '/portal/signup',
    name: 'portal-signup',
    component: () => import('@/views/portal/PortalSignupView.vue'),
  },
  {
    path: '/portal/login',
    name: 'portal-login',
    component: () => import('@/views/portal/PortalLoginView.vue'),
  },
  {
    path: '/portal/dashboard',
    name: 'portal-dashboard',
    component: () => import('@/views/portal/PortalDashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/billing/callback',
    name: 'billing-callback',
    component: () => import('@/views/portal/PortalBillingView.vue'),
  },
  {
    path: '/billing/demo-pay',
    name: 'billing-demo',
    component: () => import('@/views/portal/PortalBillingView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && token) {
    if (localStorage.getItem('ifnotus_portal') === '1') {
      return { name: 'portal-dashboard' }
    }
    return { name: 'dashboard' }
  }

  // Customer portal users land on portal dashboard, not staff WHM
  if (token && to.name === 'dashboard' && localStorage.getItem('ifnotus_portal') === '1') {
    return { name: 'portal-dashboard' }
  }

  if (token && to.meta.requiresAuth) {
    const { useAuthStore } = await import('@/stores/auth')
    const auth = useAuthStore()
    if (!auth.user) {
      try {
        await auth.fetchUser()
      } catch {
        auth.clearSession()
        return { name: 'login', query: { redirect: to.fullPath } }
      }
    }

    const requiredPermission = to.meta.permission as string | undefined
    if (requiredPermission) {
      const perms = auth.user?.permissions ?? []
      if (!auth.user?.is_superuser && !perms.includes(requiredPermission)) {
        return { name: 'dashboard' }
      }
    }
  }
})

export default router
