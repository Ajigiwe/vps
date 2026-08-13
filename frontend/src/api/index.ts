import apiClient, { transferClient } from './client'
import type { LoginRequest, User } from '@/types/auth'
import type {
  AccessAttemptEntry,
  BlockedActionEntry,
  FirewallRuleEntry,
  IpBlacklistEntry,
  SystemActionLogEntry,
} from '@/types/security'
import type {
  AlertsResponse,
  ApplicationDeploymentsResponse,
  ApplicationListResponse,
  DashboardApiResponse,
  HealthResponse,
  IntegrationsResponse,
  PortsResponse,
  ReadinessResponse,
  ServerOverview,
  ServicesResponse,
  SystemMetrics,
} from '@/types/dashboard'
import type {
  DnsCheckResponse,
  Domain,
  DomainListResponse,
  FileDetail,
  FileRootsResponse,
  FileUploadInitResponse,
  MailAlias,
  MailDomainResponse,
  Mailbox,
  SslCertificate,
  SslListResponse,
  SslReadinessResponse,
  TerminalAuditEntry,
  TerminalExecuteResponse,
} from '@/types/hosting'
import type {
  ApplicationDetail,
  ApplicationLogsResponse,
  BackupEntry,
  CronJob,
  DatabaseStatus,
  EnvironmentResponse,
  FileListResponse,
  OperationResult,
  OperationsOverview,
  SslAppStatus,
  StorageVolume,
} from '@/types/operations'

export const authApi = {
  login: (credentials: LoginRequest) =>
    apiClient.post<import('@/types/auth').LoginResponse>('/auth/login', credentials),

  verifyDevice: (body: import('@/types/auth').VerifyDeviceRequest) =>
    apiClient.post<import('@/types/auth').LoginResponse>('/auth/verify-device', body),

  probe: (body: { device_fingerprint?: string }) =>
    apiClient.post<{ message: string }>('/auth/probe', body),

  me: () => apiClient.get<User>('/auth/me'),

  logout: () => apiClient.post('/auth/logout'),

  confirmPassword: (password: string) =>
    apiClient.post<{ message: string }>('/auth/confirm-password', { password }),
}

export const securityApi = {
  blacklist: (activeOnly = true) =>
    apiClient.get<{ total: number; entries: IpBlacklistEntry[] }>('/security/blacklist', {
      params: { active_only: activeOnly },
    }),

  blockIp: (body: { ip_address: string; reason?: string; hours?: number | null }) =>
    apiClient.post<IpBlacklistEntry>('/security/blacklist', body),

  unlock: (id: string, note?: string) =>
    apiClient.post<{ message: string }>(`/security/blacklist/${id}/unlock`, { note }),

  attempts: (limit = 100) =>
    apiClient.get<{ total: number; attempts: AccessAttemptEntry[] }>('/security/attempts', {
      params: { limit },
    }),

  firewall: () =>
    apiClient.get<{ total: number; rules: FirewallRuleEntry[] }>('/security/firewall'),

  createFirewallRule: (body: { cidr: string; action: 'allow' | 'deny'; note?: string }) =>
    apiClient.post<FirewallRuleEntry>('/security/firewall', body),

  deleteFirewallRule: (id: string) =>
    apiClient.delete<{ message: string }>(`/security/firewall/${id}`),

  blockedActions: () =>
    apiClient.get<{
      total: number
      entries: BlockedActionEntry[]
      available: Array<{ key: string; label: string }>
    }>('/security/blocked-actions'),

  setBlockedAction: (body: {
    action_key: string
    enabled?: boolean
    reason?: string
    label?: string
  }) => apiClient.post<BlockedActionEntry>('/security/blocked-actions', body),

  unblockAction: (actionKey: string) =>
    apiClient.delete<{ message: string }>(`/security/blocked-actions/${encodeURIComponent(actionKey)}`),

  actionLogs: (limit = 200) =>
    apiClient.get<{ total: number; logs: SystemActionLogEntry[] }>('/security/actions', {
      params: { limit },
    }),

  clearLogs: (body: {
    confirm_password: string
    acknowledge_downloaded: boolean
    clear_attempts?: boolean
    clear_actions?: boolean
    clear_terminal?: boolean
  }) =>
    apiClient.post<{ message: string; cleared: Record<string, number> }>(
      '/security/logs/clear',
      body,
    ),
}

export const healthApi = {
  liveness: () => apiClient.get<HealthResponse>('/health'),

  readiness: () => apiClient.get<ReadinessResponse>('/health/ready'),
}

export const monitoringApi = {
  overview: () => apiClient.get<Record<string, unknown>>('/monitoring'),

  metrics: () => apiClient.get<SystemMetrics>('/monitoring/metrics'),

  integrations: () => apiClient.get<IntegrationsResponse>('/monitoring/integrations'),

  dashboard: () => apiClient.get<DashboardApiResponse>('/dashboard'),
}

export const serverApi = {
  overview: () => apiClient.get<ServerOverview>('/server/overview'),

  ports: () => apiClient.get<PortsResponse>('/server/ports'),

  services: (params?: { mode?: 'relevant' | 'all'; category?: string }) =>
    apiClient.get<ServicesResponse>('/services', { params }),

  clearCache: (reloadNginx = false) =>
    apiClient.post<OperationResult>('/server/cache/clear', null, {
      params: { reload_nginx: reloadNginx },
    }),

  refresh: (reloadNginx = true) =>
    apiClient.post<OperationResult>('/server/refresh', null, {
      params: { reload_nginx: reloadNginx },
    }),
}

export const alertsApi = {
  list: () => apiClient.get<AlertsResponse>('/alerts'),
}

export const applicationsApi = {
  list: () => apiClient.get<ApplicationListResponse>('/applications'),

  get: (appId: string) => apiClient.get<ApplicationDetail>(`/applications/${appId}`),

  logs: (appId: string, lines = 100) =>
    apiClient.get<ApplicationLogsResponse>(`/applications/${appId}/logs`, { params: { lines } }),

  clearLogs: (appId: string, confirmPassword: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/logs/clear`, {
      confirm_password: confirmPassword,
    }),

  environment: (appId: string) =>
    apiClient.get<{ timestamp: string; application_id: string; variables: Record<string, string> }>(
      `/applications/${appId}/environment`,
    ),

  revealEnvironment: (appId: string) =>
    apiClient.get<Record<string, string>>(`/applications/${appId}/environment/reveal`),

  deployments: (appId: string) =>
    apiClient.get<ApplicationDeploymentsResponse>(`/applications/${appId}/deployments`),

  gitPull: (appId: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/git/pull`),

  deploy: (
    appId: string,
    body: { version?: string; message?: string; pull?: boolean; restart?: boolean } = {},
  ) => apiClient.post<OperationResult>(`/applications/${appId}/deploy`, body),

  redeploy: (appId: string, deploymentId: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/deployments/${deploymentId}/redeploy`),

  restart: (appId: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/restart`),

  serviceAction: (appId: string, action: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/services/action`, { action }),

  setEnabled: (appId: string, enabled: boolean) =>
    apiClient.patch<OperationResult>(`/applications/${appId}`, { enabled }),

  refresh: (appId: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/refresh`),

  clearCache: (appId: string) =>
    apiClient.post<OperationResult>(`/applications/${appId}/cache/clear`),

  clearAllCaches: () =>
    apiClient.post<OperationResult>('/applications/cache/clear-all'),
}

export const operationsApi = {
  overview: () => apiClient.get<OperationsOverview>('/operations/overview'),

  environment: (reveal = false) =>
    apiClient.get<EnvironmentResponse>('/operations/environment', { params: { reveal } }),

  smtpTest: (toEmail: string) =>
    apiClient.post<OperationResult>('/operations/smtp/test', {
      to_email: toEmail,
      subject: 'IFNOTUS SMTP Test',
      body: 'Test message from IFNOTUS operations panel.',
    }),

  restartNginx: () => apiClient.post<OperationResult>('/operations/nginx/restart'),

  restartWorker: () => apiClient.post<OperationResult>('/operations/worker/restart'),

  refreshServer: () => apiClient.post<OperationResult>('/operations/server/refresh'),

  clearCentralCache: (reloadNginx = false) =>
    apiClient.post<OperationResult>('/operations/cache/clear', null, {
      params: { reload_nginx: reloadNginx },
    }),

  clearAllAppCaches: () => apiClient.post<OperationResult>('/operations/cache/clear-apps'),

  queueStatus: () =>
    apiClient.get<Array<{ queue: string; depth: number }>>('/operations/queue'),

  backups: () => apiClient.get<{ timestamp: string; backups: BackupEntry[] }>('/operations/backups'),

  createBackup: () => apiClient.post<OperationResult>('/operations/backups'),

  cron: () => apiClient.get<{ timestamp: string; jobs: CronJob[] }>('/operations/cron'),

  files: (path = '.', appId?: string) =>
    apiClient.get<FileListResponse>('/operations/files', { params: { path, app_id: appId } }),

  storage: () => apiClient.get<{ timestamp: string; volumes: StorageVolume[] }>('/operations/storage'),

  ssl: () => apiClient.get<SslAppStatus[]>('/operations/ssl'),

  database: () =>
    apiClient.get<{ timestamp: string; databases: DatabaseStatus[] }>('/operations/database'),

  databaseAction: (action: string) =>
    apiClient.post<OperationResult>(`/operations/database/${action}`),

  hostLogs: (lines = 100) =>
    apiClient.get<{ entries: Array<{ message: string; level?: string; source?: string }> }>(
      '/operations/logs/host',
      { params: { lines } },
    ),
}

export const domainsApi = {
  list: () => apiClient.get<DomainListResponse>('/domains'),

  get: (id: string) => apiClient.get<Domain>(`/domains/${id}`),

  create: (body: {
    name?: string
    subdomain_label?: string
    domain_type?: string
    parent_domain_id?: string
    application_id?: string
    document_root?: string
    proxy_port?: number
    enabled?: boolean
    force_https?: boolean
    redirect_url?: string
    provision?: boolean
    create_docroot?: boolean
    notes?: string
  }) => apiClient.post<Domain>('/domains', body),

  update: (
    id: string,
    body: Partial<{
      application_id: string | null
      document_root: string | null
      proxy_port: number | null
      enabled: boolean
      force_https: boolean
      redirect_url: string | null
      notes: string | null
      reprovision: boolean
    }>,
  ) => apiClient.patch<Domain>(`/domains/${id}`, body),

  delete: (id: string) => apiClient.delete<OperationResult>(`/domains/${id}`),

  dnsCheck: (id: string) => apiClient.post<DnsCheckResponse>(`/domains/${id}/dns-check`),

  provision: (id: string) => apiClient.post<OperationResult>(`/domains/${id}/provision`),

  importDiscovered: (body: { server_name: string; domain_type?: string; parent_domain_id?: string }) =>
    apiClient.post<Domain>('/domains/import', body),

  listRedirects: (id: string) =>
    apiClient.get<import('@/types/hosting').DomainRedirect[]>(`/domains/${id}/redirects`),

  createRedirect: (
    id: string,
    body: { source_path: string; target_url: string; status_code?: number; enabled?: boolean },
  ) => apiClient.post<import('@/types/hosting').DomainRedirect>(`/domains/${id}/redirects`, body),

  deleteRedirect: (id: string, redirectId: string) =>
    apiClient.delete<OperationResult>(`/domains/${id}/redirects/${redirectId}`),

  listDnsRecords: (id: string) =>
    apiClient.get<import('@/types/hosting').DomainDnsRecord[]>(`/domains/${id}/dns-records`),

  createDnsRecord: (
    id: string,
    body: { record_type: string; host?: string; value: string; ttl?: number; priority?: number },
  ) => apiClient.post<import('@/types/hosting').DomainDnsRecord>(`/domains/${id}/dns-records`, body),

  deleteDnsRecord: (id: string, recordId: string) =>
    apiClient.delete<OperationResult>(`/domains/${id}/dns-records/${recordId}`),
}

export const databasesApi = {
  list: () => apiClient.get<import('@/types/databases').DatabaseOverview>('/databases'),
  engines: () => apiClient.get<import('@/types/databases').EngineStatus[]>('/databases/engines'),
  create: (body: import('@/types/databases').DatabaseCreateBody) =>
    apiClient.post<import('@/types/databases').DatabaseCreated>('/databases', body),
  drop: (id: string, opts?: { confirmPassword: string; dropUser?: boolean; removeFiles?: boolean }) =>
    apiClient.post<OperationResult>(`/databases/${id}/drop`, {
      confirm_password: opts?.confirmPassword || '',
      drop_user: opts?.dropUser ?? true,
      remove_files: opts?.removeFiles ?? true,
    }),
  dropLive: (body: import('@/types/databases').DatabaseLiveDropBody) =>
    apiClient.post<OperationResult>('/databases/live/drop', body),
  adopt: (body: import('@/types/databases').DatabaseAdoptBody) =>
    apiClient.post<import('@/types/databases').DatabaseCreated>('/databases/adopt', body),
  backupManaged: (id: string) =>
    apiClient.post<import('@/types/databases').DatabaseBackup>(`/databases/${id}/backup`),
  backupLive: (body: { engine: string; name: string; path?: string }) =>
    apiClient.post<import('@/types/databases').DatabaseBackup>('/databases/live/backup', body),
  listBackups: () =>
    apiClient.get<{ backups: import('@/types/databases').DatabaseBackup[] }>('/databases/backups'),
  downloadBackupUrl: (id: string) => `/api/v1/databases/backups/${id}/download`,
  restore: (form: FormData) =>
    apiClient.post<OperationResult>('/databases/restore', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  revealPassword: (id: string) =>
    apiClient.post<{ id: string; password: string; connection_uri?: string | null }>(
      `/databases/${id}/password`,
    ),
  ensure: (engine: import('@/types/databases').DatabaseEngine) =>
    apiClient.post<OperationResult>(`/databases/engines/${engine}/ensure`),

  schema: (id: string) =>
    apiClient.get<import('@/types/databases').DbSchema>(`/databases/${id}/schema`),
  rows: (
    id: string,
    params: { table?: string; collection?: string; schema_name?: string; limit?: number; offset?: number },
  ) => apiClient.get<import('@/types/databases').DbQueryResult>(`/databases/${id}/rows`, { params }),
  query: (id: string, body: { sql?: string; script?: string; limit?: number }) =>
    apiClient.post<import('@/types/databases').DbQueryResult>(`/databases/${id}/query`, body),
  updateRow: (
    id: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      primary_key?: Record<string, unknown>
      filter?: Record<string, unknown>
      values: Record<string, unknown>
    },
  ) => apiClient.patch<import('@/types/databases').DbQueryResult>(`/databases/${id}/rows`, body),
  insertRow: (
    id: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      values: Record<string, unknown>
    },
  ) => apiClient.post<import('@/types/databases').DbQueryResult>(`/databases/${id}/rows/insert`, body),
  deleteRow: (
    id: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      primary_key?: Record<string, unknown>
      filter?: Record<string, unknown>
    },
  ) => apiClient.post<import('@/types/databases').DbQueryResult>(`/databases/${id}/rows/delete`, body),

  liveSchema: (engine: string, name: string, path?: string) =>
    apiClient.get<import('@/types/databases').DbSchema>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/schema`,
      { params: path ? { path } : undefined },
    ),
  liveRows: (
    engine: string,
    name: string,
    params: {
      table?: string
      collection?: string
      schema_name?: string
      path?: string
      limit?: number
      offset?: number
    },
  ) =>
    apiClient.get<import('@/types/databases').DbQueryResult>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/rows`,
      { params },
    ),
  liveQuery: (
    engine: string,
    name: string,
    body: { sql?: string; script?: string; limit?: number },
    path?: string,
  ) =>
    apiClient.post<import('@/types/databases').DbQueryResult>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/query`,
      body,
      { params: path ? { path } : undefined },
    ),
  liveUpdateRow: (
    engine: string,
    name: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      primary_key?: Record<string, unknown>
      filter?: Record<string, unknown>
      values: Record<string, unknown>
    },
    path?: string,
  ) =>
    apiClient.patch<import('@/types/databases').DbQueryResult>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/rows`,
      body,
      { params: path ? { path } : undefined },
    ),
  liveInsertRow: (
    engine: string,
    name: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      values: Record<string, unknown>
    },
    path?: string,
  ) =>
    apiClient.post<import('@/types/databases').DbQueryResult>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/rows/insert`,
      body,
      { params: path ? { path } : undefined },
    ),
  liveDeleteRow: (
    engine: string,
    name: string,
    body: {
      table?: string
      collection?: string
      schema_name?: string
      primary_key?: Record<string, unknown>
      filter?: Record<string, unknown>
    },
    path?: string,
  ) =>
    apiClient.post<import('@/types/databases').DbQueryResult>(
      `/databases/live/${engine}/${encodeURIComponent(name)}/rows/delete`,
      body,
      { params: path ? { path } : undefined },
    ),
}

export const sslApi = {
  list: () => apiClient.get<SslListResponse>('/ssl'),

  get: (domain: string) => apiClient.get<SslCertificate>(`/ssl/${encodeURIComponent(domain)}`),

  readiness: (domain: string) => apiClient.get<SslReadinessResponse>(`/ssl/readiness/${encodeURIComponent(domain)}`),

  issue: (body: { domain: string; email?: string; webroot?: string; dry_run?: boolean }) =>
    apiClient.post<OperationResult>('/ssl/issue', body),

  renew: (body: { domain: string; email?: string; webroot?: string; dry_run?: boolean }) =>
    apiClient.post<OperationResult>('/ssl/renew', body),

  reissue: (body: { domain: string; email?: string; webroot?: string; dry_run?: boolean }) =>
    apiClient.post<OperationResult>('/ssl/reissue', body),

  renewAll: (dryRun = false, email?: string) =>
    apiClient.post<OperationResult>('/ssl/renew-all', null, { params: { dry_run: dryRun, email } }),
}

export const mailApi = {
  getDomain: (domainId: string) => apiClient.get<MailDomainResponse>(`/mail/domains/${domainId}`),

  getSettings: () =>
    apiClient.get<{
      support_whatsapp: string
      support_url: string
      product_name: string
      auto_detect_domains: boolean
      updated_at?: string | null
    }>('/mail/settings'),

  updateSettings: (body: {
    support_whatsapp?: string
    product_name?: string
    auto_detect_domains?: boolean
  }) =>
    apiClient.put<{
      support_whatsapp: string
      support_url: string
      product_name: string
      auto_detect_domains: boolean
      updated_at?: string | null
    }>('/mail/settings', body),

  syncDomains: () => apiClient.post<OperationResult>('/mail/sync-domains'),

  ensureAuth: (domainId: string) =>
    apiClient.post<OperationResult>(`/mail/domains/${domainId}/auth`),

  syncAuth: () => apiClient.post<OperationResult>('/mail/auth/sync'),

  createMailbox: (domainId: string, body: { local_part: string; password: string; quota_mb?: number; display_name?: string }) =>
    apiClient.post<Mailbox>(`/mail/domains/${domainId}/mailboxes`, body),

  updateMailbox: (
    domainId: string,
    mailboxId: string,
    body: { password?: string; quota_mb?: number; suspended?: boolean; display_name?: string },
  ) => apiClient.patch<Mailbox>(`/mail/domains/${domainId}/mailboxes/${mailboxId}`, body),

  deleteMailbox: (domainId: string, mailboxId: string) =>
    apiClient.delete<OperationResult>(`/mail/domains/${domainId}/mailboxes/${mailboxId}`),

  createAlias: (domainId: string, body: { source_local: string; destination: string }) =>
    apiClient.post<MailAlias>(`/mail/domains/${domainId}/aliases`, body),

  deleteAlias: (domainId: string, aliasId: string) =>
    apiClient.delete<OperationResult>(`/mail/domains/${domainId}/aliases/${aliasId}`),
}

export const filesApi = {
  roots: () => apiClient.get<FileRootsResponse>('/files/roots'),

  list: (path = '.', scope?: { appId?: string; rootId?: string }) =>
    apiClient.get<FileListResponse>('/files', {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
    }),

  read: (path: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.get<FileDetail>('/files/content', {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
    }),

  write: (path: string, content: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.put<OperationResult>('/files/content', { path, content }, {
      params: { app_id: scope?.appId, root_id: scope?.rootId },
    }),

  mkdir: (path: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.post<OperationResult>('/files/mkdir', { path }, {
      params: { app_id: scope?.appId, root_id: scope?.rootId },
    }),

  move: (source: string, destination: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.post<OperationResult>('/files/move', { source, destination }, {
      params: { app_id: scope?.appId, root_id: scope?.rootId },
    }),

  delete: (path: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.delete<OperationResult>('/files', {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
    }),

  chmod: (path: string, mode: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.post<OperationResult>('/files/chmod', { path, mode }, {
      params: { app_id: scope?.appId, root_id: scope?.rootId },
    }),

  upload: (path: string, file: File, scope?: { appId?: string; rootId?: string }) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient.post<OperationResult>('/files/upload', form, {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  unzip: (path: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.post<OperationResult>('/files/unzip', null, {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
    }),

  stat: (path: string, scope?: { appId?: string; rootId?: string }) =>
    apiClient.get<FileDetail>('/files/stat', {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
    }),

  uploadChunked: async (
    file: File,
    targetPath: string,
    scope?: { appId?: string; rootId?: string },
    onProgress?: (percent: number) => void,
  ) => {
    const { data: init } = await transferClient.post<FileUploadInitResponse>(
      '/files/upload/init',
      {
        filename: file.name,
        path: targetPath,
        size_bytes: file.size,
      },
      { params: { app_id: scope?.appId, root_id: scope?.rootId } },
    )
    const chunkSize = init.chunk_size
    const totalChunks = init.total_chunks
    let uploaded = 0

    for (let index = 0; index < totalChunks; index += 1) {
      const start = index * chunkSize
      const end = Math.min(start + chunkSize, file.size)
      const chunk = file.slice(start, end)
      const form = new FormData()
      form.append('file', chunk, file.name)
      await transferClient.post('/files/upload/chunk', form, {
        params: { upload_id: init.upload_id, chunk_index: index },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      uploaded = end
      onProgress?.(Math.round((uploaded / file.size) * 100))
    }

    return transferClient.post<OperationResult>('/files/upload/complete', {
      upload_id: init.upload_id,
    })
  },

  downloadQueued: async (
    path: string,
    filename: string,
    scope?: { appId?: string; rootId?: string },
    onProgress?: (percent: number) => void,
  ) => {
    const response = await transferClient.get<Blob>('/files/download', {
      params: { path, app_id: scope?.appId, root_id: scope?.rootId },
      responseType: 'blob',
      onDownloadProgress: (ev) => {
        if (ev.total) onProgress?.(Math.round((ev.loaded / ev.total) * 100))
      },
    })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  },
}

export const inventoryApi = {
  get: () => apiClient.get<import('@/types/inventory').VpsInventoryResponse>('/inventory'),
}

export const terminalApi = {
  execute: (
    command: string,
    cwd?: string,
    options?: { scope?: import('@/types/inventory').TerminalScope; appId?: string; rootId?: string },
  ) =>
    apiClient.post<TerminalExecuteResponse>('/terminal/execute', {
      command,
      cwd,
      scope: options?.scope ?? 'ops',
      app_id: options?.appId,
      root_id: options?.rootId,
    }),

  audit: (limit = 50) => apiClient.get<TerminalAuditEntry[]>('/terminal/audit', { params: { limit } }),

  clearAudit: () => apiClient.delete<OperationResult>('/terminal/audit'),
}

export const aiApi = {
  status: () => apiClient.get<import('@/types/ai').AiSettings>('/ai/status'),
  getSettings: () => apiClient.get<import('@/types/ai').AiSettings>('/ai/settings'),
  updateSettings: (body: { api_key?: string | null; model?: string | null; clear?: boolean }) =>
    apiClient.put<import('@/types/ai').AiSettings>('/ai/settings', body),
  chat: (body: {
    message: string
    history?: import('@/types/ai').AiChatMessage[]
    surface: 'files' | 'terminal' | 'editor' | 'dashboard' | 'studio'
    path?: string
    appId?: string
    rootId?: string
    cwd?: string
    fileContent?: string
    originalContent?: string
  }) =>
    apiClient.post<import('@/types/ai').AiChatResponse>('/ai/chat', {
      message: body.message,
      history: body.history ?? [],
      surface: body.surface,
      path: body.path,
      app_id: body.appId,
      root_id: body.rootId,
      cwd: body.cwd,
      file_content: body.fileContent,
      original_content: body.originalContent,
    }),
  applyAction: (token: string) =>
    apiClient.post<OperationResult>('/ai/actions/apply', { token }),
  undoAction: () => apiClient.post<OperationResult>('/ai/actions/undo'),
  listSessions: (surface?: string, path?: string) =>
    apiClient.get<{ sessions: import('@/types/ai').AiSessionSummary[] }>('/ai/sessions', {
      params: {
        ...(surface ? { surface } : {}),
        ...(path != null ? { path } : {}),
      },
    }),
  createSession: (body: {
    surface: string
    title?: string
    path?: string
    appId?: string
    rootId?: string
  }) =>
    apiClient.post<import('@/types/ai').AiSessionDetail>('/ai/sessions', {
      surface: body.surface,
      title: body.title,
      path: body.path,
      app_id: body.appId,
      root_id: body.rootId,
    }),
  getSession: (id: string) =>
    apiClient.get<import('@/types/ai').AiSessionDetail>(`/ai/sessions/${id}`),
  deleteSession: (id: string) => apiClient.delete<OperationResult>(`/ai/sessions/${id}`),
  clearSessions: (surface?: string) =>
    apiClient.delete<OperationResult>('/ai/sessions', {
      params: surface ? { surface } : undefined,
    }),
}

export const catalogApi = {
  plans: () =>
    apiClient.get<{ items: import('@/types/platform').HostingPlan[]; brand: string; currency: string }>(
      '/catalog/plans',
    ),
  meta: () =>
    apiClient.get<{
      brand: string
      panel_name: string
      currency: string
      domain_prices: Array<{ extension: string; price_yearly: number; currency: string }>
    }>('/catalog/meta'),
}

export const customersApi = {
  register: (body: {
    email: string
    password: string
    full_name: string
    phone?: string
    company?: string
  }) =>
    apiClient.post<{
      customer: import('@/types/platform').CustomerProfile
      verification_token: string
      message: string
    }>('/customers/register', body),

  verifyEmail: (body: { token: string; code: string }) =>
    apiClient.post<import('@/types/platform').CustomerProfile>('/customers/verify-email', body),

  login: (credentials: LoginRequest) =>
    apiClient.post<import('@/types/auth').LoginResponse>('/customers/login', credentials),

  me: () => apiClient.get<import('@/types/platform').CustomerProfile>('/customers/me'),

  dashboard: () =>
    apiClient.get<import('@/types/platform').CustomerDashboard>('/customers/dashboard'),

  createOrder: (body: {
    plan_id: string
    domain_name?: string
    domain_extension?: string
    include_domain?: boolean
  }) =>
    apiClient.post<{
      order: { id: string; total_price: number; currency: string; paystack_reference?: string }
      authorization_url?: string
      reference: string
      demo: boolean
    }>('/customers/orders', body),

  verifyPayment: (reference: string) =>
    apiClient.post('/customers/orders/verify-payment', { reference }),

  checkDomain: (name: string, extension: string) =>
    apiClient.post<{
      domain: string
      available: boolean
      price_yearly: number
      message: string
      provider?: string
    }>('/customers/domains/check', { name, extension }),

  renewSubscription: (subscriptionId: string) =>
    apiClient.post<import('@/types/platform').CustomerSubscription>(
      `/customers/subscriptions/${subscriptionId}/renew`,
    ),

  changePlan: (subscriptionId: string, planId: string) =>
    apiClient.post<import('@/types/platform').CustomerSubscription>(
      `/customers/subscriptions/${subscriptionId}/change-plan`,
      { plan_id: planId },
    ),

  setAutoRenew: (subscriptionId: string, enabled: boolean) =>
    apiClient.post<import('@/types/platform').CustomerSubscription>(
      `/customers/subscriptions/${subscriptionId}/auto-renew`,
      { enabled },
    ),

  environments: () =>
    apiClient.get<import('@/types/platform').CustomerEnvironment[]>('/customers/environments'),

  notifications: () => apiClient.get('/customers/notifications'),
}
