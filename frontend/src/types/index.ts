export type Language = 'en' | 'hi' | 'hi-Latn';

export interface User {
  id: string;
  email: string;
  name: string;
  preferred_language?: Language | null;
  is_active: boolean;
  created_at: string;
}

export interface BusinessMembership {
  business_id: string;
  business_name: string;
  role: 'owner' | 'admin' | 'member';
}

export interface Business {
  id: string;
  name: string;
  timezone: string;
  default_language: Language;
  currency: string;
  settings?: Record<string, any>;
  archived_at?: string | null;
  created_at?: string;
}

export interface Customer {
  id: string;
  name: string;
  phone_e164?: string | null;
  email?: string | null;
  external_ref?: string | null;
  notes?: string | null;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Invoice {
  id: string;
  customer_id: string;
  number: string;
  total_paise: number;
  paid_paise: number;
  balance_paise: number;
  issued_on: string;
  due_on: string;
  status: 'open' | 'paid' | 'void';
  is_overdue: boolean;
  description?: string | null;
  total_display?: string;
  balance_display?: string;
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: string;
  invoice_id: string;
  amount_paise: number;
  paid_on: string;
  method: string;
  note?: string | null;
  source_action_id?: string | null;
  created_at: string;
}

export interface Reminder {
  id: string;
  customer_id: string;
  invoice_id?: string | null;
  scheduled_at: string;
  channel: 'whatsapp' | 'sms' | 'call' | 'in_app';
  status: 'scheduled' | 'due' | 'delivered' | 'failed' | 'cancelled';
  creation_source: string;
  delivery_attempts: number;
  last_error?: string | null;
  completed_at?: string | null;
  source_action_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentCommitment {
  id: string;
  customer_id: string;
  invoice_id?: string | null;
  promised_amount_paise?: number | null;
  promised_on: string;
  status: 'open' | 'kept' | 'broken' | 'cancelled';
  source_action_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PendingAction {
  id: string;
  conversation_id?: string | null;
  user_id: string;
  type: string;
  payload: Record<string, any>;
  preview: Record<string, any>;
  status: 'pending_confirmation' | 'processing' | 'completed' | 'failed' | 'cancelled' | 'expired';
  expires_at: string;
  confirmed_by?: string | null;
  result?: Record<string, any> | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  intent?: Record<string, any> | null;
  tool_metadata?: Record<string, any> | null;
  language?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  agent_id?: string | null;
  user_id: string;
  title?: string | null;
  language?: string | null;
  is_test: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  total_outstanding_paise: number;
  open_invoices_count: number;
  overdue_invoices_count: number;
  overdue_paise: number;
  customers_count: number;
  upcoming_reminders_count: number;
  due_reminders_count: number;
  collected_this_month_paise: number;
  pending_actions_count: number;
  open_commitments_count: number;
  currency?: string;
  as_of?: string;
}

export interface ActivityItem {
  id: string;
  action_type: string;
  entity_type: string;
  entity_id?: string | null;
  outcome: string;
  metadata?: Record<string, any> | null;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description?: string | null;
  language: Language;
  instructions: string;
  enabled_tools: string[];
  knowledge_sources: Array<{ type: 'note' | 'url' | 'faq'; value: string }>;
  status: 'draft' | 'active' | 'archived';
  config_version: number;
  created_at: string;
  updated_at: string;
}

export interface ApiResponse<T> {
  data: T;
  meta?: {
    page?: number;
    page_size?: number;
    total?: number;
    [key: string]: any;
  };
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: any;
  };
}

