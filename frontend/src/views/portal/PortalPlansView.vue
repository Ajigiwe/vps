<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi } from '@/api'
import type { HostingPlan } from '@/types/platform'

const router = useRouter()
const plans = ref<HostingPlan[]>([])
const loading = ref(true)
const error = ref('')
const brand = ref('IFNOTUS')

onMounted(async () => {
  try {
    const { data } = await catalogApi.plans()
    plans.value = data.items
    brand.value = data.brand
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    error.value = err.response?.data?.error?.message ?? 'Could not load plans.'
  } finally {
    loading.value = false
  }
})

function choose(plan: HostingPlan) {
  localStorage.setItem('ifnotus_selected_plan', plan.id)
  router.push({ name: 'portal-signup', query: { plan: plan.slug } })
}
</script>

<template>
  <div class="min-h-screen bg-[#f4f6f8] text-slate-800">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <div>
          <p class="text-lg font-semibold tracking-tight">{{ brand }}</p>
          <p class="text-xs text-slate-500">Cloud hosting with an AI engineer</p>
        </div>
        <div class="flex gap-3 text-sm">
          <router-link class="text-slate-600 hover:text-[#ff6c2c]" :to="{ name: 'portal-login' }">
            Customer login
          </router-link>
          <router-link
            class="rounded bg-[#ff6c2c] px-3 py-1.5 font-medium text-white hover:bg-[#e55f24]"
            :to="{ name: 'portal-signup' }"
          >
            Get started
          </router-link>
        </div>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-4 py-10">
      <div class="mb-8 max-w-2xl">
        <h1 class="text-3xl font-semibold tracking-tight text-slate-900">Hosting plans</h1>
        <p class="mt-2 text-slate-600">
          Pick a plan, add a domain, pay with Paystack, and IFNOTUS provisions your environment.
        </p>
      </div>

      <p v-if="loading" class="text-sm text-slate-500">Loading plans…</p>
      <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

      <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <article
          v-for="plan in plans"
          :key="plan.id"
          class="flex flex-col rounded border border-slate-200 bg-white p-5 shadow-sm"
        >
          <h2 class="text-lg font-semibold">{{ plan.name }}</h2>
          <p class="mt-2 text-2xl font-semibold text-[#ff6c2c]">
            GHS {{ plan.price_monthly }}
            <span class="text-sm font-normal text-slate-500">/mo</span>
          </p>
          <ul class="mt-4 flex-1 space-y-1 text-sm text-slate-600">
            <li>{{ plan.cpu_cores }} vCPU</li>
            <li>{{ plan.ram_gb }} GB RAM</li>
            <li>{{ plan.storage_gb }} GB storage</li>
            <li>{{ plan.bandwidth_tb }} TB bandwidth</li>
            <li>{{ plan.ai_credits }} AI credits</li>
          </ul>
          <button
            type="button"
            class="mt-5 rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
            @click="choose(plan)"
          >
            Choose {{ plan.name }}
          </button>
        </article>
      </div>
    </main>
  </div>
</template>
