<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api'
import { ensureDeviceFingerprint } from '@/api/client'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const approvalCode = ref('')
const emailInput = ref<HTMLInputElement | null>(null)
const codeInput = ref<HTMLInputElement | null>(null)
const fingerprint = ref<string | null>(null)
const step = ref<'credentials' | 'challenge'>('credentials')
const challengeId = ref('')
const challengeIp = ref('')
const challengeMessage = ref('')

onMounted(async () => {
  nextTick(() => emailInput.value?.focus())
  try {
    fingerprint.value = (await ensureDeviceFingerprint()) ?? null
    await authApi.probe({ device_fingerprint: fingerprint.value ?? undefined })
  } catch {
    /* probe is best-effort */
  }
})

async function finishRedirect() {
  const raw = route.query.redirect
  const candidate = Array.isArray(raw) ? raw[0] : raw
  const redirect =
    typeof candidate === 'string' &&
    candidate.startsWith('/') &&
    !candidate.startsWith('//') &&
    candidate !== '/login'
      ? candidate
      : '/'

  try {
    await router.replace(redirect)
  } catch {
    window.location.assign(redirect)
  }
}

async function handleLogin() {
  const result = await auth.login({
    email: email.value,
    password: password.value,
    device_fingerprint: fingerprint.value ?? (await ensureDeviceFingerprint().catch(() => undefined)),
  })
  if (result.ok) {
    await finishRedirect()
    return
  }
  if (result.challenge?.challenge_id) {
    challengeId.value = result.challenge.challenge_id
    challengeIp.value = result.challenge.ip_address || ''
    challengeMessage.value = result.challenge.message || ''
    step.value = 'challenge'
    approvalCode.value = ''
    nextTick(() => codeInput.value?.focus())
  }
}

async function handleVerify() {
  const ok = await auth.verifyDevice({
    challenge_id: challengeId.value,
    code: approvalCode.value.trim(),
    device_fingerprint: fingerprint.value ?? (await ensureDeviceFingerprint().catch(() => undefined)),
  })
  if (!ok) return
  await finishRedirect()
}

function backToCredentials() {
  step.value = 'credentials'
  approvalCode.value = ''
  auth.error = null
  nextTick(() => emailInput.value?.focus())
}
</script>

<template>
  <div class="login-page flex min-h-screen flex-col bg-[#f0f2f5]">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4">
        <div
          class="flex h-8 w-8 items-center justify-center rounded bg-[#ff6c2c] text-sm font-bold text-white"
          aria-hidden="true"
        >
          i
        </div>
        <div class="leading-tight">
          <p class="text-sm font-semibold text-slate-800">IFNOTUS</p>
          <p class="text-[11px] text-slate-500">Web Host Manager</p>
        </div>
      </div>
    </header>

    <main class="flex flex-1 items-center justify-center px-4 py-10">
      <form
        v-if="step === 'credentials'"
        class="w-full max-w-[420px] rounded border border-slate-200 bg-white shadow-sm"
        @submit.prevent="handleLogin"
      >
        <div class="border-b border-slate-200 bg-[#fafbfc] px-6 py-4">
          <h1 class="text-lg font-semibold text-slate-800">Log in</h1>
          <p class="mt-1 text-sm text-slate-500">
            Sign in to manage this server.
            <router-link class="text-[#ff6c2c]" :to="{ name: 'portal-plans' }">Customer portal</router-link>
          </p>
        </div>

        <div class="space-y-4 px-6 py-5">
          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-slate-700">Email</span>
            <input
              ref="emailInput"
              v-model="email"
              type="email"
              autocomplete="username"
              required
              placeholder="you@example.com"
              class="w-full rounded border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
            />
          </label>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-slate-700">Password</span>
            <input
              v-model="password"
              type="password"
              required
              autocomplete="current-password"
              placeholder="Enter your password"
              class="w-full rounded border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
            />
          </label>

          <p
            v-if="auth.error"
            class="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {{ auth.error }}
          </p>

          <button
            type="submit"
            :disabled="auth.loading"
            class="w-full rounded bg-[#ff6c2c] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e85f22] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ auth.loading ? 'Signing in…' : 'Log in' }}
          </button>
        </div>

        <div class="border-t border-slate-200 bg-[#fafbfc] px-6 py-3 text-center text-xs text-slate-500">
          Authorized access only. Activity is logged.
        </div>
      </form>

      <form
        v-else
        class="w-full max-w-[420px] rounded border border-slate-200 bg-white shadow-sm"
        @submit.prevent="handleVerify"
      >
        <div class="border-b border-slate-200 bg-[#fafbfc] px-6 py-4">
          <h1 class="text-lg font-semibold text-slate-800">Approve this device</h1>
          <p class="mt-1 text-sm text-slate-500">
            New IP detected{{ challengeIp ? `: ${challengeIp}` : '' }}. Enter the one-time code from the server.
          </p>
        </div>

        <div class="space-y-4 px-6 py-5">
          <div class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            <p class="font-medium">Challenge ID: {{ challengeId }}</p>
            <p class="mt-1 text-xs leading-relaxed">
              On the server (SSH), run:
              <code class="rounded bg-white px-1 py-0.5 text-[11px]">ifnotus-unlock pending</code>
              then type the 6-digit code below.
            </p>
          </div>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-slate-700">Approval code</span>
            <input
              ref="codeInput"
              v-model="approvalCode"
              type="text"
              inputmode="numeric"
              autocomplete="one-time-code"
              required
              maxlength="8"
              placeholder="6-digit code"
              class="w-full rounded border border-slate-300 bg-white px-3 py-2.5 text-center font-mono text-lg tracking-[0.3em] text-slate-900 placeholder:text-slate-400 focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
            />
          </label>

          <p
            v-if="auth.error"
            class="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {{ auth.error }}
          </p>

          <button
            type="submit"
            :disabled="auth.loading || approvalCode.trim().length < 4"
            class="w-full rounded bg-[#ff6c2c] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#e85f22] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ auth.loading ? 'Verifying…' : 'Verify and continue' }}
          </button>

          <button
            type="button"
            class="w-full text-sm text-slate-500 underline hover:text-slate-700"
            @click="backToCredentials"
          >
            Back to login
          </button>
        </div>
      </form>
    </main>

    <footer class="border-t border-slate-200 bg-white py-3 text-center text-xs text-slate-400">
      © {{ new Date().getFullYear() }} IFNOTUS
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  color-scheme: light;
}
</style>
