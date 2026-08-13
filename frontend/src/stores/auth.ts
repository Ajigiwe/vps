import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import type { LoginRequest, LoginResponse, User } from '@/types/auth'

export type LoginResult =
  | { ok: true }
  | { ok: false; challenge?: { challenge_id: string; ip_address?: string | null; message?: string | null } }

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!localStorage.getItem('access_token'))

  function clearSession() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    user.value = null
    error.value = null
  }

  async function applyTokens(data: LoginResponse): Promise<boolean> {
    if (!data.access_token || !data.refresh_token) {
      error.value = 'Sign in failed. Please try again.'
      return false
    }
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    // Brief retry: right after IP approval the allowlist may need a moment.
    let lastError: unknown = null
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await fetchUser()
        return true
      } catch (e) {
        lastError = e
        await new Promise((r) => setTimeout(r, 250 * (attempt + 1)))
      }
    }
    clearSession()
    const axiosErr = lastError as { response?: { data?: { error?: { message?: string } } } }
    error.value =
      axiosErr?.response?.data?.error?.message ??
      'Signed in but failed to load your profile. Please try again.'
    throw new Error(error.value)
  }

  async function login(credentials: LoginRequest): Promise<LoginResult> {
    loading.value = true
    error.value = null
    try {
      const { data } = await authApi.login(credentials)
      if (data.status === 'challenge_required' && data.challenge_id) {
        return {
          ok: false,
          challenge: {
            challenge_id: data.challenge_id,
            ip_address: data.ip_address,
            message: data.message,
          },
        }
      }
      const ok = await applyTokens(data)
      return { ok }
    } catch (e: unknown) {
      const axiosErr = e as { response?: { data?: { error?: { message?: string } } } }
      error.value =
        axiosErr.response?.data?.error?.message ??
        (e instanceof Error ? e.message : 'Sign in failed. Please try again.')
      return { ok: false }
    } finally {
      loading.value = false
    }
  }

  async function verifyDevice(payload: {
    challenge_id: string
    code: string
    device_fingerprint?: string
  }): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const { data } = await authApi.verifyDevice(payload)
      return await applyTokens(data)
    } catch (e: unknown) {
      const axiosErr = e as { response?: { data?: { error?: { message?: string } } } }
      error.value =
        axiosErr.response?.data?.error?.message ??
        (e instanceof Error ? e.message : 'Invalid or expired approval code.')
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchUser() {
    const { data } = await authApi.me()
    user.value = data
  }

  async function logout() {
    // Clear local session first so navigation/guards cannot bounce back into the app.
    const hadToken = !!localStorage.getItem('access_token')
    clearSession()
    try {
      const { useNotificationStore } = await import('@/stores/notifications')
      useNotificationStore().stopPolling()
    } catch {
      /* optional */
    }
    if (!hadToken) return
    try {
      await authApi.logout()
    } catch {
      /* Server logout is best-effort; local session is already cleared. */
    }
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    login,
    verifyDevice,
    fetchUser,
    logout,
    clearSession,
  }
})
