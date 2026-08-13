<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import { domainsApi, mailApi } from '@/api'
import { getApiErrorMessage } from '@/lib/apiError'
import { usePermissions } from '@/composables/usePermissions'
import { Permission } from '@/lib/permissions'
import type { Domain, MailAlias, Mailbox, MailDomainResponse } from '@/types/hosting'

const loading = ref(true)
const domains = ref<Domain[]>([])
const selectedId = ref('')
const mailData = ref<MailDomainResponse | null>(null)
const message = ref<{ type: 'ok' | 'err'; text: string } | null>(null)
const actionKey = ref<string | null>(null)

const mailboxForm = ref({ local_part: '', password: '', display_name: '' })
const aliasForm = ref({ source_local: '', destination: '' })
const resetPassword = ref<Record<string, string>>({})
const authHints = ref<Array<{ record_type: string; host: string; value: string; priority?: number | null }>>([])
const authBusy = ref(false)
const authStatus = ref<{
  ready?: boolean
  spf_ok?: boolean
  dkim_dns_ok?: boolean
  mx_ok?: boolean
  dkim_signing?: boolean
  messages?: string[]
  tunnel?: { submission?: string; milter?: string; sender_binding?: string }
} | null>(null)

const { can } = usePermissions()
const canWrite = computed(() => can(Permission.MAIL_WRITE))

async function loadDomains() {
  loading.value = true
  try {
    const { data } = await domainsApi.list()
    domains.value = data.domains
    if (!selectedId.value && domains.value.length) {
      selectedId.value = domains.value[0].id
    }
  } finally {
    loading.value = false
  }
}

async function loadMail() {
  if (!selectedId.value) {
    mailData.value = null
    authHints.value = []
    authStatus.value = null
    return
  }
  actionKey.value = 'load'
  mailData.value = null
  try {
    const { data } = await mailApi.getDomain(selectedId.value)
    mailData.value = data
    const auth = (data as { auth?: Record<string, unknown> | null }).auth
    if (auth) {
      applyAuth(auth)
    } else if (canWrite.value) {
      await ensureDeliveryAuth()
    }
  } catch (e) {
    mailData.value = null
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Failed to load mail config') }
  } finally {
    actionKey.value = null
  }
}

function applyAuth(auth: Record<string, unknown>) {
  authHints.value = (auth.dns as typeof authHints.value) ?? []
  authStatus.value = {
    ready: Boolean(auth.ready),
    spf_ok: Boolean(auth.spf_ok),
    dkim_dns_ok: Boolean(auth.dkim_dns_ok),
    mx_ok: Boolean(auth.mx_ok),
    dkim_signing: Boolean(auth.dkim_signing),
    messages: (auth.messages as string[]) ?? [],
    tunnel: auth.tunnel as typeof authStatus.value extends null ? never : NonNullable<typeof authStatus.value>['tunnel'],
  }
}

async function ensureDeliveryAuth() {
  if (!selectedId.value) return
  authBusy.value = true
  try {
    const { data } = await mailApi.ensureAuth(selectedId.value)
    const details = (data.details as Record<string, unknown> | undefined) ?? {}
    applyAuth(details)
    message.value = {
      type: details.ready ? 'ok' : 'err',
      text: data.message || 'Mail auth tunnel updated.',
    }
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Could not prepare mail auth') }
  } finally {
    authBusy.value = false
  }
}

async function createMailbox() {
  if (!mailboxForm.value.local_part.trim()) {
    message.value = { type: 'err', text: 'Enter the local part (before @).' }
    return
  }
  if (!mailboxForm.value.password || mailboxForm.value.password.length < 8) {
    message.value = { type: 'err', text: 'Password must be at least 8 characters.' }
    return
  }
  actionKey.value = 'mb-create'
  try {
    await mailApi.createMailbox(selectedId.value, mailboxForm.value)
    mailboxForm.value = { local_part: '', password: '', display_name: '' }
    message.value = { type: 'ok', text: 'Mailbox created — ready for IMAP/SMTP and webmail login.' }
    await loadMail()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Create failed') }
  } finally {
    actionKey.value = null
  }
}

async function toggleSuspend(mb: Mailbox) {
  actionKey.value = mb.id
  try {
    await mailApi.updateMailbox(selectedId.value, mb.id, { suspended: !mb.suspended })
    await loadMail()
  } finally {
    actionKey.value = null
  }
}

async function resetMbPassword(mb: Mailbox) {
  const pwd = resetPassword.value[mb.id]
  if (!pwd || pwd.length < 8) return
  actionKey.value = `pwd-${mb.id}`
  try {
    await mailApi.updateMailbox(selectedId.value, mb.id, { password: pwd })
    resetPassword.value[mb.id] = ''
    message.value = { type: 'ok', text: 'Password updated.' }
  } catch (e) {
    message.value = { type: 'err', text: e instanceof Error ? e.message : 'Reset failed' }
  } finally {
    actionKey.value = null
  }
}

async function deleteMailbox(mb: Mailbox) {
  if (!confirm(`Delete ${mb.email}?`)) return
  try {
    await mailApi.deleteMailbox(selectedId.value, mb.id)
    message.value = { type: 'ok', text: 'Mailbox deleted.' }
    await loadMail()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Delete failed') }
  }
}

async function createAlias() {
  actionKey.value = 'alias-create'
  try {
    await mailApi.createAlias(selectedId.value, aliasForm.value)
    aliasForm.value = { source_local: '', destination: '' }
    message.value = { type: 'ok', text: 'Alias created.' }
    await loadMail()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Create failed') }
  } finally {
    actionKey.value = null
  }
}

async function deleteAlias(alias: MailAlias) {
  try {
    await mailApi.deleteAlias(selectedId.value, alias.id)
    message.value = { type: 'ok', text: 'Alias deleted.' }
    await loadMail()
  } catch (e) {
    message.value = { type: 'err', text: getApiErrorMessage(e, 'Delete failed') }
  }
}

watch(selectedId, async () => {
  authHints.value = []
  authStatus.value = null
  await loadMail()
})
onMounted(async () => {
  await loadDomains()
  await loadMail()
})
</script>

<template>
  <DashboardLayout @refresh="() => { loadDomains(); loadMail() }">
    <div class="mail-page animate-fade-in space-y-5">
      <section class="mail-masthead overflow-hidden rounded-2xl border border-amber-900/10 bg-surface-raised shadow-card dark:border-amber-200/10">
        <div class="flex flex-col gap-5 px-5 py-6 sm:px-7 lg:flex-row lg:items-end lg:justify-between">
          <div class="flex items-center gap-4">
            <div class="mail-seal flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-amber-700/20 bg-amber-50 text-amber-800 dark:bg-amber-300/10 dark:text-amber-200">
              <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M3.5 7.5 12 13l8.5-5.5M5 18.5h14a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <div>
              <p class="mb-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-amber-700 dark:text-amber-300">Correspondence desk</p>
              <h1 class="mail-title text-2xl font-semibold text-slate-950 dark:text-white">Mail Administration</h1>
              <p class="mt-1 text-sm text-surface-muted">Manage addresses, forwarding and secure delivery from one place.</p>
            </div>
          </div>

          <label class="block w-full lg:w-80">
            <span class="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-surface-muted">Working domain</span>
            <div class="relative">
              <select
                v-model="selectedId"
                class="mail-input w-full appearance-none rounded-xl border border-surface-border bg-surface-raised px-3.5 py-2.5 pr-10 text-sm font-medium outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15"
              >
                <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.name }}</option>
              </select>
              <svg class="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-muted" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z" clip-rule="evenodd"/>
              </svg>
            </div>
          </label>
        </div>
      </section>

      <div
        v-if="message"
        class="flex items-start gap-3 rounded-xl border px-4 py-3 text-sm"
        :class="message.type === 'ok'
          ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-300'"
      >
        <span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-current" />
        <span>{{ message.text }}</span>
        <button type="button" class="ml-auto opacity-60 hover:opacity-100" aria-label="Dismiss message" @click="message = null">×</button>
      </div>

      <div v-if="loading || actionKey === 'load'" class="grid gap-4 sm:grid-cols-3">
        <div v-for="n in 3" :key="n" class="h-24 animate-pulse rounded-xl border border-surface-border bg-surface-raised" />
      </div>

      <div v-else-if="!domains.length" class="rounded-2xl border border-dashed border-surface-border bg-surface-raised px-6 py-14 text-center">
        <div class="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-slate-500/10 text-surface-muted">✉</div>
        <h2 class="mail-title text-lg font-semibold">No domain is ready for mail</h2>
        <p class="mt-1 text-sm text-surface-muted">Add a domain first, then return here to create its mailboxes.</p>
      </div>

      <template v-else-if="mailData">
        <Card padding="md" class="border-amber-700/15">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="mail-title text-base font-semibold">Outbound delivery tunnel</h2>
              <p class="mt-1 text-sm text-surface-muted">
                Webmail → TLS submission :587 → OpenDKIM sign → Postfix delivery.
                Every mailbox on this domain uses the same secured path.
              </p>
            </div>
            <button
              v-if="canWrite"
              type="button"
              class="rounded-lg border border-surface-border px-3 py-2 text-sm"
              :disabled="authBusy"
              @click="ensureDeliveryAuth"
            >
              {{ authBusy ? 'Syncing…' : 'Sync tunnel' }}
            </button>
          </div>

          <div v-if="authStatus" class="mt-4 flex flex-wrap gap-2 text-xs">
            <Badge :variant="authStatus.dkim_signing ? 'success' : 'danger'" size="sm">
              DKIM sign {{ authStatus.dkim_signing ? 'on' : 'off' }}
            </Badge>
            <Badge :variant="authStatus.spf_ok ? 'success' : 'danger'" size="sm">
              SPF {{ authStatus.spf_ok ? 'ok' : 'missing' }}
            </Badge>
            <Badge :variant="authStatus.dkim_dns_ok ? 'success' : 'danger'" size="sm">
              DKIM DNS {{ authStatus.dkim_dns_ok ? 'ok' : 'missing' }}
            </Badge>
            <Badge :variant="authStatus.mx_ok ? 'success' : 'warning'" size="sm">
              MX {{ authStatus.mx_ok ? 'ok' : 'check' }}
            </Badge>
            <Badge :variant="authStatus.ready ? 'success' : 'warning'" size="sm">
              {{ authStatus.ready ? 'Ready to send' : 'DNS publish required' }}
            </Badge>
          </div>
          <ul v-if="authStatus?.messages?.length" class="mt-3 space-y-1 text-xs text-surface-muted">
            <li v-for="(msg, i) in authStatus.messages" :key="i">• {{ msg }}</li>
          </ul>
          <p v-if="authStatus?.tunnel" class="mt-2 font-mono text-[11px] text-surface-muted">
            {{ authStatus.tunnel.submission }} · {{ authStatus.tunnel.milter }} · {{ authStatus.tunnel.sender_binding }}
          </p>

          <div v-if="authHints.length" class="mt-4 overflow-x-auto">
            <table class="min-w-full text-left text-xs">
              <thead class="text-surface-muted">
                <tr>
                  <th class="px-2 py-1.5 font-medium">Type</th>
                  <th class="px-2 py-1.5 font-medium">Host</th>
                  <th class="px-2 py-1.5 font-medium">Value</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in authHints" :key="idx" class="border-t border-surface-border align-top">
                  <td class="px-2 py-2 font-mono">{{ row.record_type }}{{ row.priority != null ? ` ${row.priority}` : '' }}</td>
                  <td class="px-2 py-2 font-mono">{{ row.host }}</td>
                  <td class="px-2 py-2 font-mono break-all">{{ row.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="mt-3 text-xs text-surface-muted">Open this domain to generate DKIM and show registrar DNS records.</p>
        </Card>

        <div class="grid gap-3 sm:grid-cols-3">
          <div class="mail-stat rounded-xl border border-surface-border bg-surface-raised p-4 shadow-card">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-surface-muted">Mailboxes</span>
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600">✉</span>
            </div>
            <p class="mail-title mt-3 text-2xl font-semibold">{{ mailData.mailboxes.length }}</p>
            <p class="mt-0.5 text-xs text-surface-muted">Professional inboxes</p>
          </div>
          <div class="mail-stat rounded-xl border border-surface-border bg-surface-raised p-4 shadow-card">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-surface-muted">Aliases</span>
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600">↗</span>
            </div>
            <p class="mail-title mt-3 text-2xl font-semibold">{{ mailData.aliases.length }}</p>
            <p class="mt-0.5 text-xs text-surface-muted">Forwarding addresses</p>
          </div>
          <div class="mail-stat rounded-xl border border-surface-border bg-surface-raised p-4 shadow-card">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-surface-muted">Service</span>
              <span class="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,.12)]" />
            </div>
            <p class="mail-title mt-3 text-lg font-semibold text-emerald-700 dark:text-emerald-300">Ready</p>
            <p class="mt-1 text-xs text-surface-muted">IMAP & SMTP configured</p>
          </div>
        </div>

        <Card padding="none" class="overflow-hidden">
          <div class="grid lg:grid-cols-[1.4fr_1fr]">
            <div class="p-5 sm:p-6">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300">Private webmail</p>
                  <h2 class="mail-title mt-1 text-xl font-semibold">{{ mailData.domain.name }}</h2>
                  <p class="mt-2 max-w-2xl text-sm leading-6 text-surface-muted">
                    Users sign in with their full email address and mailbox password. The secure web client is available as soon as this domain points to the server.
                  </p>
                </div>
                <a
                  :href="mailData.webmail_url || `https://${mailData.domain.name}/mail/`"
                  target="_blank"
                  rel="noopener"
                  class="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-slate-800 dark:bg-white dark:text-slate-950 dark:hover:bg-slate-100"
                >
                  Open webmail
                  <span aria-hidden="true">↗</span>
                </a>
              </div>
            </div>
            <div class="border-t border-surface-border bg-amber-50/50 p-5 dark:bg-amber-300/[0.03] lg:border-l lg:border-t-0">
              <p class="text-[11px] font-semibold uppercase tracking-wider text-surface-muted">Connection details</p>
              <dl class="mt-3 space-y-3 text-sm">
                <div class="flex items-center justify-between gap-4">
                  <dt class="text-surface-muted">Web</dt>
                  <dd class="truncate font-mono text-xs">{{ mailData.domain.name }}/mail</dd>
                </div>
                <div class="flex items-center justify-between gap-4 border-t border-surface-border/70 pt-3">
                  <dt class="text-surface-muted">IMAP</dt>
                  <dd class="font-mono text-xs">ifnotus.space:993 <span class="text-emerald-600">SSL</span></dd>
                </div>
                <div class="flex items-center justify-between gap-4 border-t border-surface-border/70 pt-3">
                  <dt class="text-surface-muted">SMTP</dt>
                  <dd class="font-mono text-xs">ifnotus.space:587 <span class="text-emerald-600">TLS</span></dd>
                </div>
              </dl>
            </div>
          </div>
        </Card>

        <div class="grid items-start gap-5 xl:grid-cols-[1.35fr_.65fr]">
          <Card padding="none" class="overflow-hidden">
            <div class="border-b border-surface-border p-5 sm:p-6">
              <div class="flex items-start gap-3">
                <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-500/10 text-brand-600">＋</div>
                <div>
                  <h2 class="mail-title text-lg font-semibold">Create a mailbox</h2>
                  <p class="mt-0.5 text-xs text-surface-muted">Issue a new address for {{ mailData.domain.name }}</p>
                </div>
              </div>

              <div v-if="!canWrite" class="mt-4 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                You need mail:write permission to create mailboxes.
              </div>
              <div v-else class="mt-5 grid gap-4 sm:grid-cols-2">
                <label class="block">
                  <span class="mail-label">Email address</span>
                  <div class="mt-1.5 flex rounded-xl border border-surface-border bg-transparent focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/15">
                    <input v-model="mailboxForm.local_part" placeholder="name" class="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none" />
                    <span class="flex items-center border-l border-surface-border px-3 text-xs text-surface-muted">@{{ mailData.domain.name }}</span>
                  </div>
                </label>
                <label class="block">
                  <span class="mail-label">Display name <span class="font-normal normal-case">(optional)</span></span>
                  <input v-model="mailboxForm.display_name" placeholder="e.g. Accounts Office" class="mail-input mt-1.5 w-full rounded-xl border border-surface-border bg-transparent px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15" />
                </label>
                <label class="block">
                  <span class="mail-label">Mailbox password</span>
                  <input v-model="mailboxForm.password" type="password" placeholder="Minimum 8 characters" class="mail-input mt-1.5 w-full rounded-xl border border-surface-border bg-transparent px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15" @keyup.enter="createMailbox" />
                </label>
                <div class="flex items-end">
                  <button type="button" class="w-full rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!!actionKey" @click="createMailbox">
                    {{ actionKey === 'mb-create' ? 'Creating mailbox…' : 'Create mailbox' }}
                  </button>
                </div>
              </div>
            </div>

            <div>
              <div class="flex items-center justify-between px-5 py-4 sm:px-6">
                <h3 class="text-sm font-semibold">Directory</h3>
                <Badge variant="neutral" size="sm">{{ mailData.mailboxes.length }} total</Badge>
              </div>
              <div v-if="!mailData.mailboxes.length" class="border-t border-surface-border px-6 py-10 text-center text-sm text-surface-muted">
                No mailboxes yet. Create the first address above.
              </div>
              <div v-for="mb in mailData.mailboxes" :key="mb.id" class="border-t border-surface-border px-5 py-4 sm:px-6">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div class="flex min-w-0 items-center gap-3">
                    <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-500/10 text-xs font-semibold uppercase text-slate-600 dark:text-slate-300">
                      {{ (mb.email || '?').charAt(0) }}
                    </span>
                    <div class="min-w-0">
                      <p class="truncate text-sm font-medium">{{ mb.email }}</p>
                      <Badge :variant="mb.suspended ? 'warning' : 'success'" :dot="true" size="sm" class="mt-1">
                        {{ mb.suspended ? 'Suspended' : 'Active' }}
                      </Badge>
                    </div>
                  </div>
                  <div v-if="canWrite" class="flex flex-wrap items-center gap-2 sm:justify-end">
                    <div class="flex overflow-hidden rounded-lg border border-surface-border">
                      <input v-model="resetPassword[mb.id]" type="password" placeholder="New password" class="w-32 bg-transparent px-2.5 py-1.5 text-xs outline-none sm:w-36" />
                      <button type="button" class="border-l border-surface-border px-2.5 text-xs font-medium hover:bg-slate-500/5 disabled:opacity-40" :disabled="!resetPassword[mb.id] || resetPassword[mb.id].length < 8" @click="resetMbPassword(mb)">Reset</button>
                    </div>
                    <button type="button" class="rounded-lg border border-surface-border px-2.5 py-1.5 text-xs font-medium transition hover:bg-slate-500/5" @click="toggleSuspend(mb)">
                      {{ mb.suspended ? 'Restore' : 'Suspend' }}
                    </button>
                    <button type="button" class="rounded-lg px-2.5 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-500/10" @click="deleteMailbox(mb)">Delete</button>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          <div class="space-y-5">
            <Card padding="none" class="overflow-hidden">
              <div class="border-b border-surface-border p-5">
                <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-600 dark:text-violet-300">Routing</p>
                <h2 class="mail-title mt-1 text-lg font-semibold">Aliases & forwarding</h2>
                <p class="mt-1 text-xs leading-5 text-surface-muted">Receive mail at one address and deliver it to another.</p>
              </div>
              <div v-if="canWrite" class="space-y-3 p-5">
                <label class="block">
                  <span class="mail-label">Alias address</span>
                  <div class="mt-1.5 flex rounded-xl border border-surface-border">
                    <input v-model="aliasForm.source_local" placeholder="hello" class="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none" />
                    <span class="flex items-center border-l border-surface-border px-2.5 text-[11px] text-surface-muted">@{{ mailData.domain.name }}</span>
                  </div>
                </label>
                <label class="block">
                  <span class="mail-label">Forward to</span>
                  <input v-model="aliasForm.destination" type="email" placeholder="destination@email.com" class="mail-input mt-1.5 w-full rounded-xl border border-surface-border bg-transparent px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/15" />
                </label>
                <button type="button" class="w-full rounded-xl border border-surface-border px-3 py-2.5 text-sm font-medium transition hover:border-brand-500 hover:bg-brand-500/5 disabled:opacity-50" :disabled="!!actionKey" @click="createAlias">
                  {{ actionKey === 'alias-create' ? 'Adding alias…' : 'Add forwarding alias' }}
                </button>
              </div>
              <div v-if="!mailData.aliases.length" class="border-t border-surface-border px-5 py-7 text-center text-xs text-surface-muted">No aliases configured.</div>
              <div v-for="al in mailData.aliases" :key="al.id" class="border-t border-surface-border px-5 py-3.5">
                <div class="flex items-center gap-2 text-xs">
                  <span class="min-w-0 truncate font-medium">{{ al.source_email }}</span>
                  <span class="text-surface-muted">→</span>
                  <span class="min-w-0 flex-1 truncate text-surface-muted">{{ al.destination }}</span>
                  <button v-if="canWrite" type="button" class="shrink-0 text-red-600 hover:underline" @click="deleteAlias(al)">Remove</button>
                </div>
              </div>
            </Card>

            <Card v-if="mailData.mail_config_path" padding="md">
              <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-surface-muted">System record</p>
              <h2 class="mail-title mt-1 text-base font-semibold">Mail configuration</h2>
              <p class="mt-3 break-all rounded-lg bg-slate-500/5 px-3 py-2 font-mono text-[11px] leading-5 text-surface-muted">{{ mailData.mail_config_path }}</p>
            </Card>
          </div>
        </div>
      </template>
    </div>
  </DashboardLayout>
</template>

<style scoped>
.mail-title {
  font-family: Georgia, 'Times New Roman', serif;
  letter-spacing: -0.015em;
}

.mail-masthead {
  position: relative;
}

.mail-masthead::after {
  background: repeating-linear-gradient(
    90deg,
    transparent 0,
    transparent 7px,
    rgba(146, 64, 14, 0.14) 7px,
    rgba(146, 64, 14, 0.14) 9px
  );
  bottom: 0;
  content: '';
  height: 3px;
  left: 0;
  position: absolute;
  right: 0;
}

.mail-seal {
  box-shadow: inset 0 0 0 4px rgba(146, 64, 14, 0.04);
}

.mail-label {
  display: block;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgb(var(--color-surface-muted));
}

.mail-input {
  transition: border-color 160ms ease, box-shadow 160ms ease;
}

.mail-stat {
  transition: transform 180ms ease, box-shadow 180ms ease;
}

.mail-stat:hover {
  transform: translateY(-1px);
}
</style>
