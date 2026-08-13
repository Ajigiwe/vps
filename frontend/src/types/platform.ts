export type HostingPlan = {
  id: string
  slug: string
  name: string
  cpu_cores: number
  ram_gb: number
  storage_gb: number
  bandwidth_tb: number
  ai_credits: number
  price_monthly: number
  price_yearly: number | null
  currency: string
  features: Record<string, unknown>
  sort_order: number
  is_active: boolean
}

export type CustomerProfile = {
  id: string
  email: string
  full_name: string
  phone?: string | null
  company?: string | null
  email_verified: boolean
  two_factor_enabled: boolean
  created_at: string
}

export type CustomerEnvironment = {
  id: string
  subscription_id: string
  customer_id: string
  status: string
  cpu_limit: number
  ram_limit_gb: number
  storage_limit_gb: number
  ip_address?: string | null
  domain?: string | null
  document_root?: string | null
  health_status: string
  isolation_type?: string
  container_port?: number | null
  created_at: string
}

export type CustomerSubscription = {
  id: string
  plan_id: string
  status: string
  cpu_allocated: number
  ram_allocated: number
  storage_allocated: number
  expires_at?: string | null
  auto_renew: boolean
  grace_until?: string | null
}

export type CustomerDashboard = {
  brand: string
  customer: CustomerProfile
  credits: {
    customer_id: string
    credits_remaining: number
    total_allocated: number
    lifetime_used: number
  }
  environments: CustomerEnvironment[]
  subscriptions: CustomerSubscription[]
  unread_notifications: number
  usage: Record<string, number>
}
