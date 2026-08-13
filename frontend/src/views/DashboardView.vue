<script setup lang="ts">
import { computed, ref } from 'vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import Card from '@/components/ui/Card.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import StatCard from '@/components/dashboard/StatCard.vue'
import HealthScoreRing from '@/components/dashboard/HealthScoreRing.vue'
import ServerHealthIndicator from '@/components/dashboard/ServerHealthIndicator.vue'
import ServiceStatusCard from '@/components/dashboard/ServiceStatusCard.vue'
import ApplicationStatusCard from '@/components/dashboard/ApplicationStatusCard.vue'
import AlertList from '@/components/dashboard/AlertList.vue'
import ResourceChart from '@/components/dashboard/ResourceChart.vue'
import ActivityTimeline from '@/components/dashboard/ActivityTimeline.vue'
import DeploymentList from '@/components/dashboard/DeploymentList.vue'
import QuickActions from '@/components/dashboard/QuickActions.vue'
import { serverApi } from '@/api'
import { getApiErrorMessage } from '@/lib/apiError'
import { useDashboard } from '@/composables/useDashboard'
import { IconServer } from '@/components/icons'

const { data, loading, refreshing, error, extrasError, runningServices, activeApplications, refresh } =
  useDashboard()

const primaryStats = computed(() => data.value?.stats.slice(0, 4) ?? [])
const secondaryStats = computed(() => data.value?.stats.slice(4) ?? [])

const serverBusy = ref(false)
const serverMessage = ref<{ ok: boolean; text: string } | null>(null)

async function refreshServer() {
  serverBusy.value = true
  serverMessage.value = null
  try {
    const { data: result } = await serverApi.refresh(true)
    serverMessage.value = { ok: result.success, text: result.message }
    await refresh()
  } catch (e) {
    serverMessage.value = { ok: false, text: getApiErrorMessage(e, 'Server refresh failed') }
  } finally {
    serverBusy.value = false
  }
}

async function clearCentralCache() {
  serverBusy.value = true
  serverMessage.value = null
  try {
    const { data: result } = await serverApi.clearCache(false)
    serverMessage.value = { ok: result.success, text: result.message }
    await refresh()
  } catch (e) {
    serverMessage.value = { ok: false, text: getApiErrorMessage(e, 'Cache clear failed') }
  } finally {
    serverBusy.value = false
  }
}
</script>

<template>
  <DashboardLayout :refreshing="refreshing" @refresh="refresh">
    <ErrorState v-if="error && !data" :message="error" @retry="refresh" />

    <div v-else class="animate-fade-in space-y-5 md:space-y-6">
      <!-- Hero row: health score + primary stats -->
      <section class="dashboard-grid lg:grid-cols-12" aria-label="Platform overview">
        <div class="animate-slide-up lg:col-span-3">
          <HealthScoreRing
            :score="data?.healthScore ?? 0"
            :status="data?.readiness?.status || data?.health?.status || 'degraded'"
            :environment="data?.health?.environment"
            :version="data?.health?.version"
            :loading="loading"
          />
        </div>

        <div class="dashboard-grid sm:grid-cols-2 lg:col-span-9 xl:grid-cols-4">
          <StatCard
            v-for="stat in primaryStats"
            :key="stat.id"
            :stat="stat"
            :loading="loading"
            class="animate-slide-up"
          />
        </div>
      </section>

      <!-- Secondary stats -->
      <section
        class="dashboard-grid grid-cols-2 md:grid-cols-4"
        aria-label="Infrastructure metrics"
      >
        <StatCard
          v-for="stat in secondaryStats"
          :key="stat.id"
          :stat="stat"
          :loading="loading"
        />
      </section>

      <!-- VPS inventory -->
      <section
        class="dashboard-grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7"
        aria-label="VPS inventory"
      >
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Registered apps</p>
          <p class="text-xl font-semibold">{{ data?.inventory?.registered_apps ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Discovered apps</p>
          <p class="text-xl font-semibold text-sky-600">{{ data?.inventory?.discovered_apps ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Unregistered</p>
          <p class="text-xl font-semibold text-amber-600">{{ data?.inventory?.unregistered_discovered_apps ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Domain drift</p>
          <p class="text-xl font-semibold text-amber-600">{{ data?.inventory?.domains_with_drift ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Certs expiring</p>
          <p class="text-xl font-semibold text-amber-600">{{ data?.inventory?.certificates_expiring ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Certs missing</p>
          <p class="text-xl font-semibold text-red-600">{{ data?.inventory?.certificates_missing ?? '—' }}</p>
        </Card>
        <Card padding="sm">
          <p class="text-xs text-surface-muted">Runtime issues</p>
          <p class="text-xl font-semibold">{{ data?.inventory?.runtime_issues ?? '—' }}</p>
        </Card>
      </section>

      <section aria-label="Quick actions">
        <Card title="Quick Actions" padding="sm" class="min-w-0 overflow-hidden">
          <div class="mb-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              :disabled="serverBusy"
              @click="refreshServer"
            >
              {{ serverBusy ? 'Working…' : 'Refresh server' }}
            </button>
            <button
              type="button"
              class="rounded-lg border border-surface-border px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-slate-800"
              :disabled="serverBusy"
              @click="clearCentralCache"
            >
              Clear central cache
            </button>
            <p
              v-if="serverMessage"
              class="text-xs"
              :class="serverMessage.ok ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-600'"
            >
              {{ serverMessage.text }}
            </p>
          </div>
          <QuickActions :refreshing="refreshing" @refresh="refresh" />
        </Card>
      </section>

      <!-- Charts -->
      <section class="dashboard-grid lg:grid-cols-3" aria-label="Resource utilization charts">
        <Card title="CPU Usage" subtitle="Resource utilization" class="animate-slide-up">
          <ResourceChart
            title="CPU"
            :chart="data?.charts.cpu ?? { categories: [], series: [] }"
            :loading="loading"
            unit="%"
          />
        </Card>
        <Card title="Memory Usage" subtitle="Resource utilization" class="animate-slide-up">
          <ResourceChart
            title="Memory"
            :chart="data?.charts.memory ?? { categories: [], series: [] }"
            :loading="loading"
            unit="%"
          />
        </Card>
        <Card title="Network Throughput" subtitle="Inbound / outbound" class="animate-slide-up">
          <template #actions>
            <div class="text-right text-xs text-surface-muted">
              <p>↓ {{ data?.networkThroughput.in }}</p>
              <p>↑ {{ data?.networkThroughput.out }}</p>
            </div>
          </template>
          <ResourceChart
            title="Network"
            :chart="data?.charts.network ?? { categories: [], series: [] }"
            :loading="loading"
            unit=""
          />
        </Card>
      </section>

      <!-- Servers + Services -->
      <section class="dashboard-grid items-start xl:grid-cols-2" aria-label="Servers and services">
        <Card
          title="Server Health"
          :subtitle="`${data?.servers.length ?? 0} nodes monitored`"
          class="min-w-0"
        >
          <div v-if="!data?.servers.length && !loading" class="dashboard-side-panel py-4 text-sm text-surface-muted">
            No server metrics available yet.
          </div>
          <div v-else class="dashboard-side-panel">
            <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              <ServerHealthIndicator
                v-for="server in data?.servers ?? []"
                :key="server.id"
                :server="server"
              />
            </div>
          </div>
        </Card>

        <Card
          title="Running Services"
          :subtitle="`${runningServices} of ${data?.services.length ?? 0} active`"
          class="min-w-0"
        >
          <div class="dashboard-side-panel">
            <p v-if="!data?.services.length && !loading" class="py-4 text-sm text-surface-muted">
              No managed services reported by supervisor/systemd collectors.
            </p>
            <div v-else class="dashboard-side-panel-scroll space-y-2">
              <ServiceStatusCard
                v-for="service in data?.services ?? []"
                :key="service.id"
                :service="service"
              >
                <template #icon>
                  <IconServer :size="16" class="text-brand-500" />
                </template>
              </ServiceStatusCard>
            </div>
          </div>
        </Card>
      </section>

      <!-- Applications + Alerts -->
      <section class="dashboard-grid xl:grid-cols-5" aria-label="Applications and alerts">
        <Card
          class="xl:col-span-2"
          title="Active Applications"
          :subtitle="`${activeApplications} of ${data?.applications.length ?? 0} running`"
        >
          <p v-if="!data?.applications.length && !loading" class="py-4 text-sm text-surface-muted">
            No registered applications found. Add YAML definitions under applications/ or register discovered apps.
          </p>
          <div v-else class="grid gap-2 sm:grid-cols-2">
            <ApplicationStatusCard
              v-for="app in data?.applications ?? []"
              :key="app.id"
              :application="app"
            />
          </div>
        </Card>

        <Card class="xl:col-span-3" title="Recent Alerts" subtitle="Active now">
          <AlertList :alerts="data?.alerts ?? []" :loading="loading" :max-items="8" />
        </Card>
      </section>

      <!-- Deployments + Activity -->
      <section class="dashboard-grid min-w-0 items-start xl:grid-cols-2" aria-label="Deployments and activity">
        <Card title="Recent Deployments" class="min-w-0 overflow-hidden">
          <p v-if="extrasError" class="mb-2 text-xs text-amber-600 dark:text-amber-400">{{ extrasError }}</p>
          <div class="dashboard-side-panel">
            <div class="dashboard-side-panel-scroll">
              <DeploymentList :deployments="data?.deployments ?? []" :loading="loading" />
            </div>
          </div>
        </Card>

        <Card title="Activity Timeline" subtitle="Operational events" class="min-w-0 overflow-hidden">
          <div class="dashboard-side-panel">
            <div class="dashboard-side-panel-scroll">
              <ActivityTimeline :items="data?.activities ?? []" :loading="loading" />
            </div>
          </div>
        </Card>
      </section>

      <!-- Load average footer -->
      <section
        class="flex flex-wrap items-center gap-4 rounded-xl border border-surface-border bg-surface-raised px-4 py-3 text-xs text-surface-muted"
        aria-label="Load average"
      >
        <span class="font-medium text-slate-700 dark:text-slate-200">Load average</span>
        <span v-for="(load, i) in data?.loadAverage ?? []" :key="i" class="tabular-nums">
          {{ ['1m', '5m', '15m'][i] }}: <strong class="text-slate-900 dark:text-white">{{ load }}</strong>
        </span>
      </section>
    </div>
  </DashboardLayout>
</template>
