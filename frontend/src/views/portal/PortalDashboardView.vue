<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { catalogApi, customersApi } from '@/api'
import type { CustomerDashboard, HostingPlan } from '@/types/platform'

const router = useRouter()
const dash = ref<CustomerDashboard | null>(null)
const plans = ref<HostingPlan[]>([])
const loading = ref(true)
const error = ref('')
const orderMsg = ref('')
const domainLocal = ref('')
const domainExt = ref('.online')
const domainStatus = ref('')
const selectedPlanId = ref(localStorage.getItem('Podium_selected_plan') || '')
const billingMsg = ref('')
const changePlanId = ref('')

const selectedPlan = computed(() => plans.value.find((p) => p.id === selectedPlanId.value) || plans.value[0])

function planName(planId: string) {
  return plans.value.find((p) => p.id === planId)?.name ?? 'Plan'
}

function expiryLabel(iso?: string | null) {
  if (!iso) return 'No expiry'
  return new Date(iso).toLocaleDateString()
}

onMounted(async () => {
  try {
    const [d, p] = await Promise.all([customersApi.dashboard(), catalogApi.plans()])
    dash.value = d.data
    plans.value = p.data.items
    if (!selectedPlanId.value && plans.value[0]) selectedPlanId.value = plans.value[0].id
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { error?: { message?: string } } } }
    if (err.response?.status === 401 || err.response?.status === 403) {
      localStorage.removeItem('Podium_portal')
      await router.push({ name: 'portal-login' })
      return
    }
    error.value = err.response?.data?.error?.message ?? 'Failed to load dashboard.'
  } finally {
    loading.value = false
  }
})

async function checkDomain() {
  domainStatus.value = 'Checking…'
  try {
    const { data } = await customersApi.checkDomain(domainLocal.value, domainExt.value)
    domainStatus.value = data.available
      ? `${data.domain} is available — GHS ${data.price_yearly}/yr`
      : data.message
  } catch {
    domainStatus.value = 'Domain check failed.'
  }
}

async function buy() {
  if (!selectedPlan.value) return
  orderMsg.value = 'Creating order…'
  try {
    const fullDomain = domainLocal.value
      ? `${domainLocal.value.replace(/\s+/g, '').toLowerCase()}${domainExt.value}`
      : undefined
    const { data } = await customersApi.createOrder({
      plan_id: selectedPlan.value.id,
      domain_name: fullDomain,
      domain_extension: fullDomain ? domainExt.value : undefined,
      include_domain: !!fullDomain,
    })
    if (data.demo) {
      orderMsg.value = 'Demo Paystack — verifying payment…'
      await customersApi.verifyPayment(data.reference)
      orderMsg.value = 'Payment verified. Environment provisioning started.'
      const refreshed = await customersApi.dashboard()
      dash.value = refreshed.data
    } else if (data.authorization_url) {
      window.location.href = data.authorization_url
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    orderMsg.value = err.response?.data?.error?.message ?? 'Order failed.'
  }
}

async function refreshDash() {
  const refreshed = await customersApi.dashboard()
  dash.value = refreshed.data
}

async function renew(id: string) {
  billingMsg.value = 'Renewing…'
  try {
    await customersApi.renewSubscription(id)
    await refreshDash()
    billingMsg.value = 'Subscription renewed for 30 days.'
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    billingMsg.value = err.response?.data?.error?.message ?? 'Renew failed.'
  }
}

async function toggleRenew(id: string, enabled: boolean) {
  billingMsg.value = 'Saving…'
  try {
    await customersApi.setAutoRenew(id, enabled)
    await refreshDash()
    billingMsg.value = enabled ? 'Auto-renew on.' : 'Auto-renew off.'
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    billingMsg.value = err.response?.data?.error?.message ?? 'Could not update auto-renew.'
  }
}

async function changePlan(id: string) {
  if (!changePlanId.value) return
  billingMsg.value = 'Changing plan…'
  try {
    await customersApi.changePlan(id, changePlanId.value)
    await refreshDash()
    billingMsg.value = 'Plan updated.'
  } catch (e: unknown) {
    const err = e as { response?: { data?: { error?: { message?: string } } } }
    billingMsg.value = err.response?.data?.error?.message ?? 'Plan change failed.'
  }
}

function logout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('Podium_portal')
  router.push({ name: 'portal-login' })
}
</script>

<template>
  <div class="min-h-screen bg-[#f4f6f8]">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <div>
          <p class="font-semibold">Podium Panel</p>
          <p class="text-xs text-slate-500">{{ dash?.customer.email }}</p>
        </div>
        <button type="button" class="text-sm text-slate-600 hover:text-[#ff6c2c]" @click="logout">
          Log out
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <p v-if="loading" class="text-sm text-slate-500">Loading…</p>
      <p v-else-if="error" class="text-sm text-red-600">{{ error }}</p>

      <template v-else-if="dash">
        <section class="grid gap-4 sm:grid-cols-4">
          <div class="rounded border border-slate-200 bg-white p-4">
            <p class="text-xs uppercase text-slate-500">AI credits</p>
            <p class="mt-1 text-2xl font-semibold">{{ dash.credits.credits_remaining }}</p>
          </div>
          <div class="rounded border border-slate-200 bg-white p-4">
            <p class="text-xs uppercase text-slate-500">Environments</p>
            <p class="mt-1 text-2xl font-semibold">{{ dash.environments.length }}</p>
          </div>
          <div class="rounded border border-slate-200 bg-white p-4">
            <p class="text-xs uppercase text-slate-500">Subscriptions</p>
            <p class="mt-1 text-2xl font-semibold">{{ dash.subscriptions.length }}</p>
          </div>
          <div class="rounded border border-slate-200 bg-white p-4">
            <p class="text-xs uppercase text-slate-500">Notifications</p>
            <p class="mt-1 text-2xl font-semibold">{{ dash.unread_notifications }}</p>
          </div>
        </section>

        <section class="rounded border border-slate-200 bg-white p-5">
          <h2 class="font-semibold">Your environments</h2>
          <p v-if="!dash.environments.length" class="mt-2 text-sm text-slate-500">
            No environments yet. Order a plan below.
          </p>
          <ul v-else class="mt-3 divide-y divide-slate-100">
            <li v-for="env in dash.environments" :key="env.id" class="flex items-center justify-between py-3 text-sm">
              <div>
                <p class="font-medium">{{ env.domain || env.id }}</p>
                <p class="text-slate-500">
                  {{ env.cpu_limit }} vCPU · {{ env.ram_limit_gb }} GB · {{ env.status }} ·
                  {{ env.health_status }} · {{ env.isolation_type || 'filesystem' }}
                </p>
              </div>
              <span class="rounded bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">{{ env.status }}</span>
            </li>
          </ul>
        </section>

        <section class="rounded border border-slate-200 bg-white p-5">
          <h2 class="font-semibold">Subscriptions</h2>
          <p v-if="!dash.subscriptions.length" class="mt-2 text-sm text-slate-500">
            No subscriptions yet.
          </p>
          <ul v-else class="mt-3 space-y-4">
            <li
              v-for="sub in dash.subscriptions"
              :key="sub.id"
              class="rounded border border-slate-100 p-3 text-sm"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p class="font-medium">{{ planName(sub.plan_id) }} · {{ sub.status }}</p>
                  <p class="text-slate-500">
                    {{ sub.cpu_allocated }} vCPU · {{ sub.ram_allocated }} GB · expires
                    {{ expiryLabel(sub.expires_at) }}
                    <span v-if="sub.grace_until"> · grace until {{ expiryLabel(sub.grace_until) }}</span>
                  </p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    type="button"
                    class="rounded bg-[#ff6c2c] px-3 py-1.5 text-xs font-medium text-white"
                    @click="renew(sub.id)"
                  >
                    Renew 30 days
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-300 px-3 py-1.5 text-xs"
                    @click="toggleRenew(sub.id, !sub.auto_renew)"
                  >
                    {{ sub.auto_renew ? 'Turn off auto-renew' : 'Turn on auto-renew' }}
                  </button>
                </div>
              </div>
              <div class="mt-3 flex flex-wrap items-center gap-2">
                <select v-model="changePlanId" class="rounded border border-slate-300 px-2 py-1.5 text-xs">
                  <option value="">Upgrade / downgrade to…</option>
                  <option v-for="p in plans" :key="p.id" :value="p.id" :disabled="p.id === sub.plan_id">
                    {{ p.name }} — GHS {{ p.price_monthly }}/mo
                  </option>
                </select>
                <button
                  type="button"
                  class="rounded border border-slate-300 px-3 py-1.5 text-xs"
                  @click="changePlan(sub.id)"
                >
                  Apply plan
                </button>
              </div>
            </li>
          </ul>
          <p v-if="billingMsg" class="mt-2 text-sm text-slate-700">{{ billingMsg }}</p>
        </section>

        <section class="rounded border border-slate-200 bg-white p-5">
          <h2 class="font-semibold">Order hosting</h2>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <label class="block text-sm">
              <span class="mb-1 block text-slate-600">Plan</span>
              <select v-model="selectedPlanId" class="w-full rounded border border-slate-300 px-3 py-2">
                <option v-for="p in plans" :key="p.id" :value="p.id">
                  {{ p.name }} — GHS {{ p.price_monthly }}/mo
                </option>
              </select>
            </label>
            <div class="grid grid-cols-[1fr_auto] gap-2">
              <label class="block text-sm">
                <span class="mb-1 block text-slate-600">Domain (optional)</span>
                <input v-model="domainLocal" placeholder="mystudio" class="w-full rounded border border-slate-300 px-3 py-2" />
              </label>
              <label class="block text-sm">
                <span class="mb-1 block text-slate-600">TLD</span>
                <select v-model="domainExt" class="rounded border border-slate-300 px-2 py-2">
                  <option>.online</option>
                  <option>.com</option>
                  <option>.net</option>
                </select>
              </label>
            </div>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button type="button" class="rounded border border-slate-300 px-3 py-2 text-sm" @click="checkDomain">
              Check domain
            </button>
            <button type="button" class="rounded bg-[#ff6c2c] px-3 py-2 text-sm font-medium text-white" @click="buy">
              Pay & provision
            </button>
          </div>
          <p v-if="domainStatus" class="mt-2 text-sm text-slate-600">{{ domainStatus }}</p>
          <p v-if="orderMsg" class="mt-2 text-sm text-slate-700">{{ orderMsg }}</p>
        </section>
      </template>
    </main>
  </div>
</template>
