<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import { applicationsApi, domainsApi } from '@/api'
import { getApiErrorMessage } from '@/lib/apiError'
import { usePermissions } from '@/composables/usePermissions'
import { Permission } from '@/lib/permissions'
import type { ApplicationSummary } from '@/types/dashboard'
import type { DnsCheckResponse, Domain } from '@/types/hosting'
import type { NginxDiscoveredDomain } from '@/types/inventory'

type Tab = 'domains' | 'subdomains' | 'aliases' | 'redirects' | 'dns' | 'discovered'

const loading = ref(true)
const domains = ref<Domain[]>([])
const discoveredDomains = ref<NginxDiscoveredDomain[]>([])
const driftCount = ref(0)
const availablePorts = ref<number[]>([])
const listeningPorts = ref<number[]>([])
const serverIp = ref<string | null>(null)
const apps = ref<ApplicationSummary[]>([])
const message = ref<{ type: 'ok' | 'err'; text: string } | null>(null)
const actionKey = ref<string | null>(null)
const dnsResult = ref<DnsCheckResponse | null>(null)
const showForm = ref(false)
const tab = ref<Tab>('domains')
const selectedId = ref<string | null>(null)

const form = ref({
  name: '',
  subdomain_label: '',
  domain_type: 'primary' as Domain['domain_type'],
  parent_domain_id: '',
  application_id: '',
  document_root: '',
  proxy_port: '' as string | number,
  force_https: false,
  redirect_url: '',
  notes: '',
  provision: true,
})

const redirectForm = ref({ source_path: '/', target_url: '', status_code: 301 })
const dnsForm = ref({ record_type: 'A', host: '@', value: '', ttl: 3600, priority: '' as string | number })

const { can } = usePermissions()
const canWrite = computed(() => can(Permission.DOMAINS_WRITE))

const primaryDomains = computed(() =>
  domains.value.filter((d) => d.domain_type === 'primary' || d.domain_type === 'addon'),
)

const subdomainDomains = computed(() => domains.value.filter((d) => d.domain_type === 'subdomain'))
const aliasDomains = computed(() =>
  domains.value.filter((d) => d.domain_type === 'alias' || d.domain_type === 'redirect'),
)

const filteredDomains = computed(() => {
  if (tab.value === 'subdomains') return subdomainDomains.value
  if (tab.value === 'aliases') return aliasDomains.value
  if (tab.value === 'domains') return primaryDomains.value
  return domains.value
})

function parentName(domain: Domain): string | null {
  if (!domain.parent_domain_id) return null
  return domains.value.find((d) => d.id === domain.parent_domain_id)?.name ?? null
}

const selected = computed(() => domains.value.find((d) => d.id === selectedId.value) || null)

async function load() {
  loading.value = true
  try {
    const d = await domainsApi.list()
    domains.value = d.data.domains
    discoveredDomains.value = d.data.discovered ?? []
    driftCount.value = d.data.drift_count ?? 0
    availablePorts.value = d.data.available_ports ?? []
    listeningPorts.value = d.data.listening_ports ?? []
    serverIp.value = d.data.server_ip ?? null
    if (selectedId.value && !domains.value.some((x) => x.id === selectedId.value)) {
      selectedId.value = null
    }
  } finally {
    loading.value = false
  }
  // Apps are only needed for the create form dropdown — don't block the page.
  applicationsApi
    .list()
    .then((a) => {
      apps.value = a.data.applications
    })
    .catch(() => {
      apps.value = []
    })
}

function openCreate(type: Domain['domain_type']) {
  form.value = {
    name: '',
    subdomain_label: '',
    domain_type: type,
    parent_domain_id: primaryDomains.value[0]?.id || '',
    application_id: '',
    document_root: '',
    proxy_port: '',
    force_https: false,
    redirect_url: '',
    notes: '',
    provision: true,
  }
  showForm.value = true
  if (type === 'subdomain') tab.value = 'subdomains'
  else if (type === 'alias' || type === 'redirect') tab.value = 'aliases'
  else tab.value = 'domains'
}

async function createDomain() {
  actionKey.value = 'create'
  message.value = null
  try {
    const portRaw = form.value.proxy_port
    const proxyPort =
      portRaw === '' || portRaw === null || portRaw === undefined ? undefined : Number(portRaw)
    await domainsApi.create({
      name: form.value.name || undefined,
      subdomain_label: form.value.subdomain_label || undefined,
      domain_type: form.value.domain_type,
      parent_domain_id: form.value.parent_domain_id || undefined,
      application_id: form.value.application_id || undefined,
      document_root: form.value.document_root || undefined,
      proxy_port: Number.isFinite(proxyPort) ? proxyPort : undefined,
      force_https: form.value.force_https,
      redirect_url: form.value.redirect_url || undefined,
      notes: form.value.notes || undefined,
      provision: form.value.provision,
      create_docroot: true,
    })
    message.value = { type: 'ok', text: 'Domain created and nginx provisioned.' }
    showForm.value = false
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Failed to create domain') }
  } finally {
    actionKey.value = null
  }
}

async function toggleEnabled(domain: Domain) {
  actionKey.value = domain.id
  try {
    await domainsApi.update(domain.id, { enabled: !domain.enabled, reprovision: true })
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Update failed') }
  } finally {
    actionKey.value = null
  }
}

async function toggleHttps(domain: Domain) {
  actionKey.value = `https-${domain.id}`
  try {
    await domainsApi.update(domain.id, { force_https: !domain.force_https, reprovision: true })
    message.value = { type: 'ok', text: `Force HTTPS ${!domain.force_https ? 'on' : 'off'}.` }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'HTTPS update failed') }
  } finally {
    actionKey.value = null
  }
}

async function provision(domain: Domain) {
  actionKey.value = `prov-${domain.id}`
  try {
    const { data } = await domainsApi.provision(domain.id)
    message.value = { type: data.success ? 'ok' : 'err', text: data.message }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Provision failed') }
  } finally {
    actionKey.value = null
  }
}

async function checkDns(domain: Domain) {
  actionKey.value = `dns-${domain.id}`
  dnsResult.value = null
  try {
    const { data } = await domainsApi.dnsCheck(domain.id)
    dnsResult.value = data
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'DNS check failed') }
  } finally {
    actionKey.value = null
  }
}

async function removeDomain(domain: Domain) {
  if (!confirm(`Delete ${domain.name}? This removes the nginx site IFNOTUS created.`)) return
  actionKey.value = `del-${domain.id}`
  try {
    await domainsApi.delete(domain.id)
    message.value = { type: 'ok', text: 'Domain deleted.' }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Delete failed') }
  } finally {
    actionKey.value = null
  }
}

async function importSite(site: NginxDiscoveredDomain) {
  actionKey.value = `imp-${site.server_name}`
  try {
    await domainsApi.importDiscovered({ server_name: site.server_name })
    message.value = { type: 'ok', text: `Imported ${site.server_name}.` }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Import failed') }
  } finally {
    actionKey.value = null
  }
}

async function addRedirect() {
  if (!selected.value) return
  actionKey.value = 'redir'
  try {
    await domainsApi.createRedirect(selected.value.id, {
      source_path: redirectForm.value.source_path || '/',
      target_url: redirectForm.value.target_url,
      status_code: Number(redirectForm.value.status_code) || 301,
    })
    redirectForm.value = { source_path: '/', target_url: '', status_code: 301 }
    message.value = { type: 'ok', text: 'Redirect created and nginx updated.' }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Redirect failed') }
  } finally {
    actionKey.value = null
  }
}

async function removeRedirect(redirectId: string) {
  if (!selected.value) return
  actionKey.value = `rdel-${redirectId}`
  try {
    await domainsApi.deleteRedirect(selected.value.id, redirectId)
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Delete redirect failed') }
  } finally {
    actionKey.value = null
  }
}

async function addDns() {
  if (!selected.value) return
  actionKey.value = 'dnsadd'
  try {
    const priority =
      dnsForm.value.priority === '' || dnsForm.value.priority === null
        ? undefined
        : Number(dnsForm.value.priority)
    await domainsApi.createDnsRecord(selected.value.id, {
      record_type: dnsForm.value.record_type,
      host: dnsForm.value.host || '@',
      value: dnsForm.value.value,
      ttl: Number(dnsForm.value.ttl) || 3600,
      priority,
    })
    dnsForm.value = { record_type: 'A', host: '@', value: serverIp.value || '', ttl: 3600, priority: '' }
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'DNS record failed') }
  } finally {
    actionKey.value = null
  }
}

async function removeDns(recordId: string) {
  if (!selected.value) return
  try {
    await domainsApi.deleteDnsRecord(selected.value.id, recordId)
    await load()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Delete DNS failed') }
  }
}

function dnsBadge(domain: Domain) {
  if (domain.dns_points_here === true) return { variant: 'success' as const, label: 'DNS OK' }
  if (domain.dns_points_here === false) return { variant: 'danger' as const, label: 'DNS mismatch' }
  return { variant: 'neutral' as const, label: 'DNS unknown' }
}

onMounted(load)
</script>

<template>
  <DashboardLayout @refresh="load">
    <div class="animate-fade-in space-y-5">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="text-lg font-semibold text-slate-900 dark:text-white">Domains</h1>
          <p class="text-sm text-surface-muted">
            cPanel-style domains, subdomains, aliases, redirects &amp; DNS hints
            <span v-if="serverIp"> · server IP {{ serverIp }}</span>
            <span v-if="driftCount" class="text-amber-600"> · {{ driftCount }} drift</span>
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" class="rounded-lg border border-surface-border px-3 py-2 text-sm" :disabled="loading" @click="load">
            Refresh
          </button>
          <template v-if="canWrite">
            <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white" @click="openCreate('primary')">
              Add domain
            </button>
            <button type="button" class="rounded-lg border border-surface-border px-3 py-2 text-sm" @click="openCreate('subdomain')">
              Add subdomain
            </button>
            <button type="button" class="rounded-lg border border-surface-border px-3 py-2 text-sm" @click="openCreate('alias')">
              Add alias
            </button>
          </template>
        </div>
      </div>

      <p
        v-if="message"
        class="rounded-lg px-3 py-2 text-sm"
        :class="message.type === 'ok' ? 'bg-emerald-500/10 text-emerald-700' : 'bg-red-500/10 text-red-700'"
      >
        {{ message.text }}
      </p>

      <div class="flex flex-wrap gap-1 border-b border-surface-border pb-1">
        <button
          v-for="t in [
            { id: 'domains', label: `Domains (${primaryDomains.length})` },
            { id: 'subdomains', label: `Subdomains (${subdomainDomains.length})` },
            { id: 'aliases', label: `Aliases / Redirects (${aliasDomains.length})` },
            { id: 'redirects', label: 'Path redirects' },
            { id: 'dns', label: 'DNS zone' },
            { id: 'discovered', label: `Discovered (${discoveredDomains.length})` },
          ]"
          :key="t.id"
          type="button"
          class="rounded-lg px-3 py-1.5 text-sm"
          :class="tab === t.id ? 'bg-brand-500/10 text-brand-700 dark:text-brand-300' : 'text-surface-muted hover:bg-slate-100 dark:hover:bg-slate-800'"
          @click="tab = t.id as Tab"
        >
          {{ t.label }}
        </button>
      </div>

      <Card v-if="showForm && canWrite" padding="md">
        <h2 class="mb-3 text-sm font-semibold">
          New {{ form.domain_type }}
        </h2>
        <div class="grid gap-3 md:grid-cols-2">
          <label v-if="form.domain_type === 'subdomain'" class="block text-sm">
            <span class="text-surface-muted">Subdomain label</span>
            <input v-model="form.subdomain_label" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 font-mono text-sm" placeholder="blog" />
          </label>
          <label v-else class="block text-sm">
            <span class="text-surface-muted">Hostname</span>
            <input v-model="form.name" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2" placeholder="example.com" />
          </label>
          <label class="block text-sm">
            <span class="text-surface-muted">Type</span>
            <select v-model="form.domain_type" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option value="primary">Primary domain</option>
              <option value="addon">Addon domain</option>
              <option value="subdomain">Subdomain</option>
              <option value="alias">Alias / parked</option>
              <option value="redirect">Domain redirect</option>
            </select>
          </label>
          <label v-if="form.domain_type !== 'primary' && form.domain_type !== 'addon'" class="block text-sm md:col-span-2">
            <span class="text-surface-muted">Parent domain</span>
            <select v-model="form.parent_domain_id" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option value="">Select parent</option>
              <option v-for="p in primaryDomains" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <p v-if="form.domain_type === 'subdomain' && form.subdomain_label && form.parent_domain_id" class="mt-1 font-mono text-xs text-surface-muted">
              → {{ form.subdomain_label }}.{{ primaryDomains.find((p) => p.id === form.parent_domain_id)?.name }}
            </p>
          </label>
          <label v-if="form.domain_type === 'redirect'" class="block text-sm md:col-span-2">
            <span class="text-surface-muted">Redirect to URL</span>
            <input v-model="form.redirect_url" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2" placeholder="https://example.com/" />
          </label>
          <label v-if="form.domain_type !== 'redirect'" class="block text-sm md:col-span-2">
            <span class="text-surface-muted">Document root</span>
            <input v-model="form.document_root" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2 font-mono text-sm" placeholder="/var/www/example.com" />
          </label>
          <label v-if="form.domain_type !== 'redirect'" class="block text-sm">
            <span class="text-surface-muted">Proxy port (optional)</span>
            <select v-model="form.proxy_port" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option value="">None — static files</option>
              <option v-for="port in availablePorts" :key="port" :value="port">{{ port }}</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="text-surface-muted">Application</span>
            <select v-model="form.application_id" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option value="">None</option>
              <option v-for="a in apps" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-sm md:col-span-2">
            <input v-model="form.force_https" type="checkbox" class="rounded border-surface-border" />
            Force HTTPS redirect (when SSL cert exists)
          </label>
          <label class="flex items-center gap-2 text-sm md:col-span-2">
            <input v-model="form.provision" type="checkbox" class="rounded border-surface-border" />
            Create nginx site + document root now
          </label>
        </div>
        <div class="mt-4 flex gap-2">
          <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white" :disabled="actionKey === 'create'" @click="createDomain">
            {{ actionKey === 'create' ? 'Creating…' : 'Create & provision' }}
          </button>
          <button type="button" class="rounded-lg border border-surface-border px-3 py-2 text-sm" @click="showForm = false">Cancel</button>
        </div>
      </Card>

      <Card v-if="dnsResult" padding="sm">
        <p class="text-sm font-medium">DNS: {{ dnsResult.domain }}</p>
        <p class="text-xs text-surface-muted">
          {{ dnsResult.resolves ? dnsResult.addresses.join(', ') : dnsResult.message || 'Does not resolve' }}
          <span v-if="dnsResult.points_to_server !== null"> · points here: {{ dnsResult.points_to_server ? 'yes' : 'no' }}</span>
        </p>
      </Card>

      <!-- Domains / Subdomains / Aliases lists -->
      <div v-if="tab === 'domains' || tab === 'subdomains' || tab === 'aliases'" class="space-y-2">
        <div v-if="loading" class="text-sm text-surface-muted">Loading…</div>
        <div v-else-if="!filteredDomains.length" class="rounded-xl border border-dashed border-surface-border p-8 text-center text-sm text-surface-muted">
          Nothing here yet.
        </div>
        <div
          v-for="domain in filteredDomains"
          :key="domain.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-surface-border bg-surface-raised px-4 py-3"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium text-slate-900 dark:text-white">{{ domain.name }}</span>
              <Badge size="sm">{{ domain.domain_type }}</Badge>
              <Badge :variant="domain.enabled ? 'success' : 'neutral'" size="sm">{{ domain.enabled ? 'Enabled' : 'Disabled' }}</Badge>
              <Badge :variant="dnsBadge(domain).variant" size="sm">{{ dnsBadge(domain).label }}</Badge>
              <Badge v-if="domain.nginx_enabled !== null" :variant="domain.nginx_enabled ? 'info' : 'warning'" size="sm">
                nginx {{ domain.nginx_enabled ? 'on' : 'off' }}
              </Badge>
              <Badge v-if="domain.force_https" size="sm" variant="success">HTTPS</Badge>
            </div>
            <p class="mt-1 text-xs text-surface-muted">
              <span v-if="parentName(domain)">of {{ parentName(domain) }} · </span>
              <span v-if="domain.document_root">{{ domain.document_root }}</span>
              <span v-if="domain.proxy_port"> · :{{ domain.proxy_port }}</span>
              <span v-if="domain.redirect_url"> · → {{ domain.redirect_url }}</span>
              <span v-if="domain.nginx_site"> · site {{ domain.nginx_site }}</span>
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs" @click="checkDns(domain)">Check DNS</button>
            <button v-if="canWrite" type="button" class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs" @click="provision(domain)">Re-provision</button>
            <button v-if="canWrite" type="button" class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs" @click="toggleHttps(domain)">
              {{ domain.force_https ? 'Disable HTTPS force' : 'Force HTTPS' }}
            </button>
            <button v-if="canWrite" type="button" class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs" @click="toggleEnabled(domain)">
              {{ domain.enabled ? 'Disable' : 'Enable' }}
            </button>
            <button
              v-if="canWrite"
              type="button"
              class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs"
              @click="selectedId = domain.id; tab = 'redirects'"
            >
              Redirects
            </button>
            <button
              v-if="canWrite"
              type="button"
              class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs"
              @click="selectedId = domain.id; tab = 'dns'; dnsForm.value = serverIp || ''"
            >
              DNS
            </button>
            <button v-if="canWrite" type="button" class="rounded-lg border border-red-500/30 px-2.5 py-1.5 text-xs text-red-600" @click="removeDomain(domain)">
              Delete
            </button>
          </div>
        </div>
      </div>

      <!-- Path redirects -->
      <div v-else-if="tab === 'redirects'" class="space-y-4">
        <Card padding="md">
          <label class="block text-sm">
            <span class="text-surface-muted">Select domain</span>
            <select v-model="selectedId" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option :value="null">Choose…</option>
              <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </label>
          <div v-if="selected && canWrite" class="mt-4 grid gap-3 md:grid-cols-3">
            <input v-model="redirectForm.source_path" class="rounded-lg border border-surface-border bg-transparent px-3 py-2 font-mono text-sm" placeholder="/old" />
            <input v-model="redirectForm.target_url" class="rounded-lg border border-surface-border bg-transparent px-3 py-2 text-sm" placeholder="https://…" />
            <div class="flex gap-2">
              <select v-model="redirectForm.status_code" class="rounded-lg border border-surface-border bg-transparent px-3 py-2 text-sm">
                <option :value="301">301</option>
                <option :value="302">302</option>
              </select>
              <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white" @click="addRedirect">Add</button>
            </div>
          </div>
          <ul v-if="selected" class="mt-4 space-y-2 text-sm">
            <li v-for="r in selected.redirects || []" :key="r.id" class="flex justify-between gap-2 rounded-lg border border-surface-border px-3 py-2">
              <span class="font-mono text-xs">{{ r.status_code }} {{ r.source_path }} → {{ r.target_url }}</span>
              <button v-if="canWrite" type="button" class="text-xs text-red-600" @click="removeRedirect(r.id)">Remove</button>
            </li>
            <li v-if="!(selected.redirects || []).length" class="text-surface-muted">No path redirects.</li>
          </ul>
        </Card>
      </div>

      <!-- DNS zone editor -->
      <div v-else-if="tab === 'dns'" class="space-y-4">
        <Card padding="md">
          <p class="mb-3 text-xs text-surface-muted">
            These are the records you should set at your domain registrar. IFNOTUS does not host DNS — it tracks intended records and verifies A-records point here.
          </p>
          <label class="block text-sm">
            <span class="text-surface-muted">Select domain</span>
            <select v-model="selectedId" class="mt-1 w-full rounded-lg border border-surface-border bg-transparent px-3 py-2">
              <option :value="null">Choose…</option>
              <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </label>
          <div v-if="selected && canWrite" class="mt-4 grid gap-2 md:grid-cols-5">
            <select v-model="dnsForm.record_type" class="rounded-lg border border-surface-border bg-transparent px-2 py-2 text-sm">
              <option>A</option><option>AAAA</option><option>CNAME</option><option>MX</option><option>TXT</option>
            </select>
            <input v-model="dnsForm.host" class="rounded-lg border border-surface-border bg-transparent px-2 py-2 font-mono text-sm" placeholder="@" />
            <input v-model="dnsForm.value" class="rounded-lg border border-surface-border bg-transparent px-2 py-2 font-mono text-sm md:col-span-2" :placeholder="serverIp || 'value'" />
            <button type="button" class="rounded-lg bg-brand-600 px-3 py-2 text-sm text-white" @click="addDns">Add</button>
          </div>
          <div v-if="selected" class="mt-4 overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead class="text-xs uppercase text-surface-muted">
                <tr><th class="py-2">Type</th><th>Host</th><th>Value</th><th>TTL</th><th></th></tr>
              </thead>
              <tbody>
                <tr v-for="r in selected.dns_records || []" :key="r.id" class="border-t border-surface-border/60">
                  <td class="py-2 font-mono text-xs">{{ r.record_type }}</td>
                  <td class="font-mono text-xs">{{ r.host }}</td>
                  <td class="max-w-[240px] truncate font-mono text-xs">{{ r.value }}</td>
                  <td class="text-xs">{{ r.ttl }}</td>
                  <td>
                    <button v-if="canWrite" type="button" class="text-xs text-red-600" @click="removeDns(r.id)">Remove</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!(selected.dns_records || []).length" class="mt-2 text-sm text-surface-muted">No DNS hints yet.</p>
          </div>
        </Card>
      </div>

      <!-- Discovered -->
      <div v-else class="space-y-2">
        <div
          v-for="site in discoveredDomains"
          :key="site.server_name + site.site_path"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed border-surface-border bg-surface-raised/50 px-4 py-3"
        >
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-medium">{{ site.server_name }}</span>
              <Badge size="sm" variant="info">discovered</Badge>
              <Badge :variant="site.enabled ? 'success' : 'warning'" size="sm">nginx {{ site.enabled ? 'on' : 'off' }}</Badge>
              <Badge v-if="site.ssl_enabled" size="sm" variant="success">SSL</Badge>
            </div>
            <p class="mt-1 text-xs text-surface-muted">
              <span v-if="site.document_root">root {{ site.document_root }}</span>
              <span v-if="site.proxy_pass"> · {{ site.proxy_pass }}</span>
            </p>
          </div>
          <button
            v-if="canWrite"
            type="button"
            class="rounded-lg bg-brand-600 px-3 py-1.5 text-xs text-white"
            @click="importSite(site)"
          >
            Import to IFNOTUS
          </button>
        </div>
        <p v-if="!discoveredDomains.length" class="text-sm text-surface-muted">No unmanaged nginx hostnames found.</p>
      </div>
    </div>
  </DashboardLayout>
</template>
