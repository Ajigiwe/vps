<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import { healthApi, monitoringApi, serverApi, aiApi, mailApi } from '@/api'
import { REALTIME_POLL_MS } from '@/config/polling'
import { useAuthStore } from '@/stores/auth'
import { usePolling } from '@/composables/usePolling'
import { Permission } from '@/lib/permissions'
import { usePermissions } from '@/composables/usePermissions'
import Skeleton from '@/components/ui/Skeleton.vue'
import { getApiErrorMessage } from '@/lib/apiError'
import type { IntegrationsResponse, PortsResponse, ReadinessResponse } from '@/types/dashboard'
import type { AiSettings } from '@/types/ai'

interface WebmailSettings {
  support_whatsapp: string
  support_url: string
  product_name: string
  auto_detect_domains: boolean
  updated_at?: string | null
}

const router = useRouter()
const auth = useAuthStore()
const { can } = usePermissions()
const canManageSecurity = computed(() => can(Permission.SYSTEM_ADMIN) || !!auth.user?.is_superuser)

const { data: readiness, refresh: refreshReadiness } = usePolling<ReadinessResponse>(
  async () => (await healthApi.readiness()).data,
  REALTIME_POLL_MS,
)

const { data: ports, refresh: refreshPorts } = usePolling<PortsResponse>(
  async () => (await serverApi.ports()).data,
  REALTIME_POLL_MS,
  { requiresAuth: true },
)

const { data: integrations, refresh: refreshIntegrations } = usePolling<IntegrationsResponse>(
  async () => (await monitoringApi.integrations()).data,
  REALTIME_POLL_MS,
  { requiresAuth: true },
)

const aiSettings = ref<AiSettings | null>(null)
const aiLoading = ref(false)
const aiSaving = ref(false)
const aiKey = ref('')
const aiModel = ref('deepseek-chat')
const aiMessage = ref<{ ok: boolean; text: string } | null>(null)
const canManageAi = computed(() => can(Permission.SYSTEM_ADMIN) || !!auth.user?.is_superuser)

const webmailSettings = ref<WebmailSettings | null>(null)
const webmailLoading = ref(false)
const webmailSaving = ref(false)
const webmailWhatsapp = ref('+233541069241')
const webmailProduct = ref('Podium Webmail')
const webmailAutoDetect = ref(true)
const webmailMessage = ref<{ ok: boolean; text: string } | null>(null)
const canManageWebmail = computed(() => can(Permission.SYSTEM_ADMIN) || !!auth.user?.is_superuser)

const integrationEntries = computed(() => {
  if (!integrations.value) return []
  return Object.entries(integrations.value).map(([name, info]) => ({
    name,
    configured: info.configured,
    status: String(info.status ?? 'unknown'),
  }))
})

const displayName = computed(
  () => auth.user?.full_name || auth.user?.username || 'Operator',
)

const userInitial = computed(() =>
  (auth.user?.username || 'U').charAt(0).toUpperCase(),
)

function formatRole(role: string) {
  return role
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

async function loadProfile() {
  if (!auth.user) {
    try {
      await auth.fetchUser()
    } catch {
      /* profile load optional on settings page */
    }
  }
}

async function loadAiSettings() {
  if (!canManageAi.value) return
  aiLoading.value = true
  aiMessage.value = null
  try {
    const { data } = await aiApi.getSettings()
    aiSettings.value = data
    aiModel.value = data.model || 'deepseek-chat'
  } catch (e) {
    aiMessage.value = { ok: false, text: getApiErrorMessage(e, 'Failed to load AI settings') }
  } finally {
    aiLoading.value = false
  }
}

async function saveAiSettings() {
  aiSaving.value = true
  aiMessage.value = null
  try {
    const body: { api_key?: string; model?: string; clear?: boolean } = {
      model: aiModel.value.trim() || 'deepseek-chat',
    }
    if (aiKey.value.trim()) body.api_key = aiKey.value.trim()
    const { data } = await aiApi.updateSettings(body)
    aiSettings.value = data
    aiKey.value = ''
    aiMessage.value = { ok: true, text: 'SNR Dev settings saved.' }
  } catch (e) {
    aiMessage.value = { ok: false, text: getApiErrorMessage(e, 'Failed to save AI settings') }
  } finally {
    aiSaving.value = false
  }
}

async function clearAiKey() {
  if (!confirm('Remove the stored SNR Dev API key?')) return
  aiSaving.value = true
  try {
    const { data } = await aiApi.updateSettings({ clear: true })
    aiSettings.value = data
    aiKey.value = ''
    aiMessage.value = { ok: true, text: 'API key cleared.' }
  } catch (e) {
    aiMessage.value = { ok: false, text: getApiErrorMessage(e, 'Failed to clear API key') }
  } finally {
    aiSaving.value = false
  }
}

async function loadWebmailSettings() {
  if (!canManageWebmail.value) return
  webmailLoading.value = true
  webmailMessage.value = null
  try {
    const { data } = await mailApi.getSettings()
    webmailSettings.value = data
    webmailWhatsapp.value = data.support_whatsapp || '+233541069241'
    webmailProduct.value = data.product_name || 'Podium Webmail'
    webmailAutoDetect.value = data.auto_detect_domains !== false
  } catch (e) {
    webmailMessage.value = { ok: false, text: getApiErrorMessage(e, 'Failed to load webmail settings') }
  } finally {
    webmailLoading.value = false
  }
}

async function saveWebmailSettings() {
  webmailSaving.value = true
  webmailMessage.value = null
  try {
    const { data } = await mailApi.updateSettings({
      support_whatsapp: webmailWhatsapp.value.trim(),
      product_name: webmailProduct.value.trim() || 'Podium Webmail',
      auto_detect_domains: webmailAutoDetect.value,
    })
    webmailSettings.value = data
    webmailMessage.value = {
      ok: true,
      text: `Saved. Support opens WhatsApp: ${data.support_url}`,
    }
  } catch (e) {
    webmailMessage.value = { ok: false, text: getApiErrorMessage(e, 'Failed to save webmail settings') }
  } finally {
    webmailSaving.value = false
  }
}

async function syncWebmailDomains() {
  webmailSaving.value = true
  webmailMessage.value = null
  try {
    const { data } = await mailApi.syncDomains()
    webmailMessage.value = {
      ok: data.success,
      text: data.message || 'Webmail domain sync finished.',
    }
  } catch (e) {
    webmailMessage.value = { ok: false, text: getApiErrorMessage(e, 'Domain sync failed') }
  } finally {
    webmailSaving.value = false
  }
}

async function handleLogout() {
  await auth.logout()
  await router.replace({ name: 'login' })
}

function refreshAll() {
  refreshReadiness()
  refreshPorts()
  refreshIntegrations()
  loadProfile()
  loadAiSettings()
  loadWebmailSettings()
}

onMounted(refreshAll)
</script>

<template>
  <DashboardLayout @refresh="refreshAll">
    <div class="animate-fade-in space-y-5">
      <Card padding="none">
        <div class="divide-y divide-surface-border">
          <div v-if="auth.user" class="flex items-center gap-4 p-4 md:p-5">
            <div
              class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-500/15 text-lg font-semibold text-brand-700 dark:text-brand-300"
              aria-hidden="true"
            >
              {{ userInitial }}
            </div>
            <div class="min-w-0 flex-1">
              <p class="truncate text-base font-semibold text-slate-900 dark:text-white">
                {{ displayName }}
              </p>
              <p class="truncate text-sm text-surface-muted">@{{ auth.user.username }}</p>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <Badge
                  v-for="role in auth.user.roles"
                  :key="role"
                  variant="info"
                  size="sm"
                >
                  {{ formatRole(role) }}
                </Badge>
              </div>
            </div>
          </div>
          <div v-else class="p-5">
            <p class="text-sm text-surface-muted">Loading profile…</p>
          </div>

          <dl v-if="auth.user" class="divide-y divide-surface-border text-sm">
            <div class="grid grid-cols-[6.5rem_1fr] items-center gap-x-4 px-4 py-3 md:px-5">
              <dt class="text-surface-muted">Username</dt>
              <dd class="font-medium text-slate-900 dark:text-white">{{ auth.user.username }}</dd>
            </div>
            <div class="grid grid-cols-[6.5rem_1fr] items-center gap-x-4 px-4 py-3 md:px-5">
              <dt class="text-surface-muted">Email</dt>
              <dd class="truncate font-medium text-slate-900 dark:text-white">
                {{ auth.user.email }}
              </dd>
            </div>
            <div class="grid grid-cols-[6.5rem_1fr] items-center gap-x-4 px-4 py-3 md:px-5">
              <dt class="text-surface-muted">Status</dt>
              <dd>
                <Badge :variant="auth.user.is_active ? 'success' : 'danger'" dot size="sm">
                  {{ auth.user.is_active ? 'Active' : 'Inactive' }}
                </Badge>
              </dd>
            </div>
          </dl>

          <div class="flex justify-end bg-slate-50/80 px-4 py-3 dark:bg-slate-900/40 md:px-5">
            <button
              type="button"
              class="rounded-lg px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-500/10 dark:text-red-400"
              @click="handleLogout"
            >
              Sign out
            </button>
          </div>
        </div>
      </Card>

      <Card title="Platform Health">
        <div class="mb-4 flex flex-wrap gap-4">
          <div>
            <p class="text-xs text-surface-muted">Readiness</p>
            <Badge
              :variant="readiness?.status === 'healthy' ? 'success' : 'warning'"
              dot
              class="mt-1"
            >
              {{ readiness?.status ?? '—' }}
            </Badge>
          </div>
          <div>
            <p class="text-xs text-surface-muted">Environment</p>
            <p class="font-medium">{{ readiness?.environment ?? '—' }}</p>
          </div>
          <div>
            <p class="text-xs text-surface-muted">Version</p>
            <p class="font-medium">{{ readiness?.version ?? '—' }}</p>
          </div>
        </div>

        <div class="space-y-2">
          <div
            v-for="component in readiness?.components ?? []"
            :key="component.name"
            class="flex items-center justify-between rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-900"
          >
            <span class="font-medium capitalize">{{ component.name }}</span>
            <div class="flex items-center gap-3">
              <span v-if="component.latency_ms" class="text-xs text-surface-muted">
                {{ component.latency_ms.toFixed(1) }} ms
              </span>
              <Badge :variant="component.status === 'healthy' ? 'success' : 'danger'" dot>
                {{ component.status }}
              </Badge>
            </div>
          </div>
        </div>
      </Card>

      <Card title="SNR Dev" subtitle="Server companion for Files, Terminal & Editor">
        <div v-if="!canManageAi" class="text-sm text-surface-muted">
          Only superadmins can manage the SNR Dev API key.
        </div>
        <div v-else-if="aiLoading" class="space-y-3">
          <Skeleton height="2.5rem" />
          <Skeleton height="2.5rem" />
          <Skeleton height="2.5rem" width="40%" />
        </div>
        <div v-else class="space-y-4">
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <Badge :variant="aiSettings?.configured ? 'success' : 'warning'" dot size="sm">
              {{ aiSettings?.configured ? 'Configured' : 'Not configured' }}
            </Badge>
            <span v-if="aiSettings?.api_key_masked" class="font-mono text-xs text-surface-muted">
              {{ aiSettings.api_key_masked }}
            </span>
          </div>

          <label class="block text-sm">
            <span class="text-surface-muted">API key</span>
            <input
              v-model="aiKey"
              type="password"
              autocomplete="off"
              class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 font-mono text-sm"
              :placeholder="aiSettings?.configured ? '•••• leave blank to keep current key' : 'sk-…'"
            />
          </label>

          <label class="block text-sm">
            <span class="text-surface-muted">Model</span>
            <input
              v-model="aiModel"
              class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 text-sm"
              placeholder="chat model id"
            />
          </label>

          <p
            v-if="aiMessage"
            class="text-sm"
            :class="aiMessage.ok ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-600'"
          >
            {{ aiMessage.text }}
          </p>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              :disabled="aiSaving"
              @click="saveAiSettings"
            >
              {{ aiSaving ? 'Saving…' : 'Save' }}
            </button>
            <button
              v-if="aiSettings?.configured"
              type="button"
              class="rounded-lg border border-surface-border px-4 py-2 text-sm disabled:opacity-50"
              :disabled="aiSaving"
              @click="clearAiKey"
            >
              Clear key
            </button>
          </div>
        </div>
      </Card>

      <Card
        title="Webmail"
        subtitle="Support WhatsApp + auto-detect domains for /mail on every site"
      >
        <div v-if="!canManageWebmail" class="text-sm text-surface-muted">
          Only administrators can manage webmail settings.
        </div>
        <div v-else-if="webmailLoading" class="space-y-3">
          <Skeleton height="2.5rem" />
          <Skeleton height="2.5rem" />
        </div>
        <div v-else class="space-y-4">
          <p class="text-sm text-surface-muted">
            The Support link in Roundcube opens WhatsApp chat. New nginx domains get
            <span class="font-mono">/mail</span> automatically (same idea as app/database discovery).
          </p>

          <label class="block text-sm">
            <span class="text-surface-muted">Support WhatsApp number</span>
            <input
              v-model="webmailWhatsapp"
              type="tel"
              class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 font-mono text-sm"
              placeholder="+233541069241"
            />
          </label>

          <label class="block text-sm">
            <span class="text-surface-muted">Product name</span>
            <input
              v-model="webmailProduct"
              class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 text-sm"
              placeholder="Podium Webmail"
            />
          </label>

          <label class="flex items-center gap-2 text-sm">
            <input v-model="webmailAutoDetect" type="checkbox" class="rounded border-surface-border" />
            <span>Auto-detect new domains and expose <span class="font-mono">/mail</span></span>
          </label>

          <p
            v-if="webmailSettings?.support_url"
            class="text-xs text-surface-muted"
          >
            Preview:
            <a
              :href="webmailSettings.support_url"
              target="_blank"
              rel="noopener"
              class="font-mono text-brand-700 underline dark:text-brand-300"
            >{{ webmailSettings.support_url }}</a>
          </p>

          <p
            v-if="webmailMessage"
            class="text-sm"
            :class="webmailMessage.ok ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-600'"
          >
            {{ webmailMessage.text }}
          </p>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              :disabled="webmailSaving"
              @click="saveWebmailSettings"
            >
              {{ webmailSaving ? 'Saving…' : 'Save webmail' }}
            </button>
            <button
              type="button"
              class="rounded-lg border border-surface-border px-4 py-2 text-sm disabled:opacity-50"
              :disabled="webmailSaving"
              @click="syncWebmailDomains"
            >
              Sync /mail now
            </button>
          </div>
        </div>
      </Card>

      <Card title="Integrations" subtitle="Live collector status">
        <div class="space-y-2">
          <div
            v-for="item in integrationEntries"
            :key="item.name"
            class="flex items-center justify-between rounded-lg bg-slate-100 px-3 py-2 text-sm dark:bg-slate-900"
          >
            <span class="font-medium capitalize">{{ item.name }}</span>
            <div class="flex items-center gap-2">
              <span class="text-xs text-surface-muted">
                {{ item.configured ? 'configured' : 'not configured' }}
              </span>
              <Badge
                :variant="
                  item.status === 'healthy'
                    ? 'success'
                    : item.status === 'degraded'
                      ? 'warning'
                      : 'neutral'
                "
                dot
                size="sm"
              >
                {{ item.status }}
              </Badge>
            </div>
          </div>
        </div>
      </Card>

      <Card
        v-if="canManageSecurity"
        title="Access security"
        subtitle="Firewall, login logs, and action audit"
      >
        <p class="mb-3 text-sm text-surface-muted">
          Manage IP allow/deny networks, login traces (web / CLI / SSH), action audit, and action kill-switches.
        </p>
        <button
          type="button"
          class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          @click="router.push({ name: 'security' })"
        >
          Open Security & Audit
        </button>
      </Card>

      <Card title="Monitored Ports" subtitle="Services Podium tracks for outages">
        <p class="mb-3 text-sm text-surface-muted">
          Expected:
          <span class="font-mono">{{ ports?.expected_ports?.join(', ') ?? '—' }}</span>
        </p>
        <div
          v-if="ports?.missing_ports?.length"
          class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300"
        >
          Not listening: {{ ports.missing_ports.join(', ') }}
        </div>
        <p v-else class="text-sm text-emerald-600 dark:text-emerald-400">
          All expected ports are listening.
        </p>
      </Card>
    </div>
  </DashboardLayout>
</template>
