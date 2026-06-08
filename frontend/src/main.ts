import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import './style.css'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()

// Register all Element Plus icons
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus)

// 全局捕获 Vue 渲染异常
app.config.errorHandler = (err, instance, info) => {
  const msg = err instanceof Error ? err.message : String(err)
  if (msg.includes('getBoundingClientRect') || msg.includes('Cannot read properties of null')) {
    console.warn('[Vue] 忽略 DOM 测量错误:', msg)
    return
  }
  console.error('[Vue]', err, instance, info)
}

// 全局 window 异常兜底（防止非 Vue 异常崩溃页面）
window.addEventListener('error', (e) => {
  if (e.message?.includes('getBoundingClientRect') || e.message?.includes('Cannot read properties of null')) {
    console.warn('[Window] 已拦截 DOM 错误:', e.message)
    e.preventDefault()
    e.stopPropagation()
    return false
  }
})

app.mount('#app')

const authStore = useAuthStore()
if (authStore.isLoggedIn) {
  authStore.fetchUser().catch(err => console.error('初始化用户信息失败:', err))
}
