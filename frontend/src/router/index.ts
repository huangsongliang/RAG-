import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '../components/ChatPage.vue'
import AuthPage from '../components/AuthPage.vue'
import DocumentManager from '../components/DocumentManager.vue'
import NotificationCenter from '../components/NotificationCenter.vue'
import AuditLog from '../components/AuditLog.vue'
import PermissionManager from '../components/PermissionManager.vue'
import WorkflowEditor from '../components/WorkflowEditor.vue'
import PluginMarket from '../components/PluginMarket.vue'
import DataMigration from '../components/DataMigration.vue'
import KnowledgeGraphPage from '../components/KnowledgeGraphPage.vue'
import MultimodalPage from '../components/MultimodalPage.vue'
import GithubCallback from '../components/GithubCallback.vue'
import DemoPage from '../components/DemoPage.vue'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/',
    name: 'Chat',
    component: ChatPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/documents',
    name: 'Documents',
    component: DocumentManager,
    meta: { requiresAuth: true },
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: NotificationCenter,
    meta: { requiresAuth: true },
  },
  {
    path: '/audit',
    name: 'Audit',
    component: AuditLog,
    meta: { requiresAuth: true },
  },
  {
    path: '/permissions',
    name: 'Permissions',
    component: PermissionManager,
    meta: { requiresAuth: true },
  },
  {
    path: '/workflow',
    name: 'Workflow',
    component: WorkflowEditor,
    meta: { requiresAuth: true },
  },
    {
      path: '/plugins',
      name: 'Plugins',
      component: PluginMarket,
      meta: { requiresAuth: true },
    },
    {
      path: '/data-migration',
      name: 'DataMigration',
      component: DataMigration,
      meta: { requiresAuth: true },
    },
    {
      path: '/knowledge-graph',
      name: 'KnowledgeGraph',
      component: KnowledgeGraphPage,
      meta: { requiresAuth: true },
    },
    {
      path: '/multimodal',
      name: 'Multimodal',
      component: MultimodalPage,
      meta: { requiresAuth: true },
    },
    {
      path: '/demo',
    name: 'Demo',
    component: DemoPage,
  },
  {
    path: '/login',
    name: 'Login',
    component: AuthPage,
  },
  {
    path: '/register',
    name: 'Register',
    component: AuthPage,
  },
  {
    path: '/github/callback',
    name: 'GithubCallback',
    component: GithubCallback,
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: AuthPage,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
  } else if ((to.path === '/login' || to.path === '/register') && authStore.isLoggedIn) {
    next('/')
  } else {
    next()
  }
})

// 监听 Token 过期事件（来自 request.ts 的 401 自动刷新失败）
window.addEventListener('auth:logout', () => {
  const authStore = useAuthStore()
  authStore.logout()
  router.push('/login')
})

export default router
