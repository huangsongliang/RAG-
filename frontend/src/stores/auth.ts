import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { get, post, clearAuthTokens } from '../utils/request'
import { useChatStore } from './chat'

export interface User {
  id: number
  username: string
  email?: string
  phone?: string
  roles: string[]
  permissions: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token') || null)
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token') || null)
  const user = ref<User | null>(null)
  const isLoggedIn = computed(() => !!accessToken.value)

  function setTokens(access: string, refresh?: string) {
    accessToken.value = access
    localStorage.setItem('access_token', access)
    if (refresh) {
      refreshToken.value = refresh
      localStorage.setItem('refresh_token', refresh)
    }
  }

  async function login(email: string, password: string): Promise<void> {
    const data = await post<{ access_token: string; refresh_token?: string }>('/api/auth/login', {
      email,
      password,
    })
    setTokens(data.access_token, data.refresh_token)
    await fetchUser()
    const chatStore = useChatStore()
    await chatStore.fetchSessions()
  }

  async function loginWithPhone(phone: string, code: string): Promise<void> {
    const data = await post<{ access_token: string; refresh_token?: string }>('/api/auth/login/phone', {
      phone,
      code,
    })
    setTokens(data.access_token, data.refresh_token)
    await fetchUser()
    const chatStore = useChatStore()
    await chatStore.fetchSessions()
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    await post('/api/auth/register', { username, email, password })
  }

  async function registerWithPhone(phone: string, code: string, password?: string): Promise<void> {
    await post('/api/auth/register/phone', { phone, code, password })
  }

  async function sendSmsCode(phone: string): Promise<void> {
    await post('/api/auth/sms/send', { phone })
  }

  async function fetchUser(): Promise<void> {
    if (!accessToken.value) return
    try {
      const u = await get<User>('/api/auth/me')
      user.value = u
    } catch {
      logout()
    }
  }

  async function refreshAccessToken(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const data = await post<{ access_token: string }>('/api/auth/refresh', {
        refresh_token: refreshToken.value,
      })
      accessToken.value = data.access_token
      localStorage.setItem('access_token', data.access_token)
      return true
    } catch {
      logout()
      return false
    }
  }

  function logout(): void {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    clearAuthTokens()
  }

  function getAuthHeader(): Record<string, string> {
    if (!accessToken.value) return {}
    return { Authorization: `Bearer ${accessToken.value}` }
  }

  return {
    accessToken,
    refreshToken,
    user,
    isLoggedIn,
    login,
    loginWithPhone,
    register,
    registerWithPhone,
    sendSmsCode,
    fetchUser,
    refreshAccessToken,
    logout,
    getAuthHeader,
  }
})
