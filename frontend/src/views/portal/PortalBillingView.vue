<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { customersApi } from '@/api'

const route = useRoute()
const router = useRouter()
const message = ref('Confirming your payment…')

onMounted(async () => {
  const reference = String(route.query.reference || route.query.ref || '')
  if (!reference) {
    message.value = 'No payment reference found.'
    return
  }
  try {
    await customersApi.verifyPayment(reference)
    message.value = 'Payment confirmed. Opening your panel…'
    await router.replace({ name: 'portal-dashboard' })
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    message.value = err.response?.data?.error?.message ?? 'Payment confirmation failed.'
  }
})
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-[#f4f6f8] px-4">
    <div class="w-full max-w-md rounded border border-slate-200 bg-white p-6 text-center">
      <p class="font-semibold">IFNOTUS billing</p>
      <p class="mt-3 text-sm text-slate-600">{{ message }}</p>
    </div>
  </div>
</template>
