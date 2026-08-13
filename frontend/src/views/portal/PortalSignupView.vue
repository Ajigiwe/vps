<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { customersApi } from '@/api'

const router = useRouter()
const fullName = ref('')
const email = ref('')
const password = ref('')
const phone = ref('')
const loading = ref(false)
const error = ref('')
const verifyToken = ref('')
const verifyCode = ref('')
const step = ref<'register' | 'verify'>('register')
const message = ref('')

async function register() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await customersApi.register({
      email: email.value,
      password: password.value,
      full_name: fullName.value,
      phone: phone.value || undefined,
    })
    verifyToken.value = data.verification_token
    message.value = data.message
    // Demo: code is embedded in token as customer_id:CODE:exp:sig
    const parts = data.verification_token.split(':')
    if (parts.length === 4) verifyCode.value = parts[1]
    step.value = 'verify'
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    error.value = err.response?.data?.error?.message ?? 'Registration failed.'
  } finally {
    loading.value = false
  }
}

async function verify() {
  loading.value = true
  error.value = ''
  try {
    await customersApi.verifyEmail({ token: verifyToken.value, code: verifyCode.value })
    router.push({ name: 'portal-login', query: { verified: '1' } })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    error.value = err.response?.data?.error?.message ?? 'Verification failed.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-[#f4f6f8] px-4">
    <form
      class="w-full max-w-md rounded border border-slate-200 bg-white p-6 shadow-sm"
      @submit.prevent="step === 'register' ? register() : verify()"
    >
      <h1 class="text-xl font-semibold text-slate-900">
        {{ step === 'register' ? 'Create Podium account' : 'Verify email' }}
      </h1>
      <p class="mt-1 text-sm text-slate-500">
        {{ step === 'register' ? 'Customer signup for hosting.' : message }}
      </p>

      <div v-if="step === 'register'" class="mt-5 space-y-3">
        <input
          v-model="fullName"
          required
          placeholder="Full name"
          class="w-full rounded border border-slate-300 px-3 py-2.5 text-sm focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
        />
        <input
          v-model="email"
          type="email"
          required
          placeholder="Email"
          class="w-full rounded border border-slate-300 px-3 py-2.5 text-sm focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
        />
        <input
          v-model="password"
          type="password"
          required
          minlength="8"
          placeholder="Password"
          class="w-full rounded border border-slate-300 px-3 py-2.5 text-sm focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
        />
        <input
          v-model="phone"
          placeholder="Phone (optional)"
          class="w-full rounded border border-slate-300 px-3 py-2.5 text-sm focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
        />
      </div>
      <div v-else class="mt-5 space-y-3">
        <input
          v-model="verifyCode"
          required
          placeholder="6-digit code"
          class="w-full rounded border border-slate-300 px-3 py-2.5 text-sm focus:border-[#ff6c2c] focus:outline-none focus:ring-2 focus:ring-[#ff6c2c]/25"
        />
        <p class="text-xs text-slate-500">Demo builds show the code automatically.</p>
      </div>

      <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
      <button
        type="submit"
        class="mt-5 w-full rounded bg-[#ff6c2c] py-2.5 text-sm font-semibold text-white disabled:opacity-60"
        :disabled="loading"
      >
        {{ loading ? 'Please wait…' : step === 'register' ? 'Create account' : 'Verify & continue' }}
      </button>
      <p class="mt-3 text-center text-sm text-slate-500">
        Already have an account?
        <router-link class="text-[#ff6c2c]" :to="{ name: 'portal-login' }">Log in</router-link>
      </p>
    </form>
  </div>
</template>
