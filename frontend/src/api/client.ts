import { ApiResponse, Language } from '../types';

const BASE_URL = '/api';

class ApiClient {
  private token: string | null = null;
  private refreshToken: string | null = null;
  private businessId: string | null = null;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  constructor() {
    this.token = localStorage.getItem('chotu_access_token');
    this.refreshToken = localStorage.getItem('chotu_refresh_token');
    this.businessId = localStorage.getItem('chotu_business_id');
  }

  setSession(token: string, refreshToken: string) {
    this.token = token;
    this.refreshToken = refreshToken;
    localStorage.setItem('chotu_access_token', token);
    localStorage.setItem('chotu_refresh_token', refreshToken);
  }

  setBusinessId(id: string) {
    this.businessId = id;
    localStorage.setItem('chotu_business_id', id);
  }

  clearSession() {
    this.token = null;
    this.refreshToken = null;
    this.businessId = null;
    localStorage.removeItem('chotu_access_token');
    localStorage.removeItem('chotu_refresh_token');
    localStorage.removeItem('chotu_business_id');
  }

  getToken(): string | null {
    return this.token || localStorage.getItem('chotu_access_token');
  }

  getBusinessId(): string | null {
    return this.businessId || localStorage.getItem('chotu_business_id');
  }

  private onRefreshed(token: string) {
    this.refreshSubscribers.forEach((cb) => cb(token));
    this.refreshSubscribers = [];
  }

  private async tryRefreshToken(): Promise<string | null> {
    if (!this.refreshToken) return null;
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (!res.ok) {
        this.clearSession();
        return null;
      }
      const data = await res.json();
      const newTokens = data.data.tokens;
      this.setSession(newTokens.access_token, newTokens.refresh_token);
      return newTokens.access_token;
    } catch {
      this.clearSession();
      return null;
    }
  }

  async request<T>(
    endpoint: string,
    options: RequestInit = {},
    requireBusiness: boolean = true
  ): Promise<ApiResponse<T>> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const currentToken = this.token || localStorage.getItem('chotu_access_token');
    if (currentToken) {
      headers['Authorization'] = `Bearer ${currentToken}`;
    }

    const currentBizId = this.businessId || localStorage.getItem('chotu_business_id');
    if (requireBusiness && currentBizId) {
      headers['X-Business-ID'] = currentBizId;
    }

    let res = await fetch(`${BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });

    // Handle token refresh on 401
    if (res.status === 401 && this.refreshToken && !endpoint.includes('/auth/refresh') && !endpoint.includes('/auth/login')) {
      if (!this.isRefreshing) {
        this.isRefreshing = true;
        const newToken = await this.tryRefreshToken();
        this.isRefreshing = false;
        if (newToken) {
          this.onRefreshed(newToken);
          headers['Authorization'] = `Bearer ${newToken}`;
          res = await fetch(`${BASE_URL}${endpoint}`, {
            ...options,
            headers,
          });
        }
      } else {
        // Wait for active refresh
        await new Promise<void>((resolve) => {
          this.refreshSubscribers.push((newToken) => {
            headers['Authorization'] = `Bearer ${newToken}`;
            resolve();
          });
        });
        res = await fetch(`${BASE_URL}${endpoint}`, {
          ...options,
          headers,
        });
      }
    }

    const json = await res.json().catch(() => ({}));

    if (!res.ok) {
      const errorMsg = json?.error?.message || `Request failed with status ${res.status}`;
      const err = new Error(errorMsg);
      (err as any).status = res.status;
      (err as any).details = json?.error?.details;
      (err as any).code = json?.error?.code;
      throw err;
    }

    return json;
  }

  // --- Auth endpoints ---
  async login(email: string, password: string) {
    const res = await this.request<any>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }, false);
    this.setSession(res.data.tokens.access_token, res.data.tokens.refresh_token);
    return res.data;
  }

  async register(data: { email: string; password: string; name: string; preferred_language?: string }) {
    const res = await this.request<any>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }, false);
    this.setSession(res.data.tokens.access_token, res.data.tokens.refresh_token);
    return res.data;
  }

  async me() {
    return this.request<any>('/auth/me', {}, false);
  }

  async patchMe(data: { name?: string; preferred_language?: string; current_password?: string; new_password?: string }) {
    return this.request<any>('/auth/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }, false);
  }

  async logout() {
    try {
      if (this.refreshToken) {
        await this.request('/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: this.refreshToken }),
        }, false);
      }
    } finally {
      this.clearSession();
    }
  }

  // --- Businesses ---
  async getBusinessMe() {
    return this.request<any>('/businesses/me');
  }

  async createBusiness(data: { name: string; timezone?: string; default_language?: string }) {
    return this.request<any>('/businesses', {
      method: 'POST',
      body: JSON.stringify(data),
    }, false);
  }

  async patchBusinessMe(data: Record<string, any>) {
    return this.request<any>('/businesses/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getMembers() {
    return this.request<any>('/members');
  }

  async inviteMember(data: { email: string; role: 'admin' | 'member' }) {
    return this.request<any>('/members/invite', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // --- Dashboard ---
  async getDashboardSummary() {
    return this.request<any>('/dashboard/summary');
  }

  async getDashboardActivity(page = 1, pageSize = 15) {
    return this.request<any>(`/dashboard/activity?page=${page}&page_size=${pageSize}`);
  }

  async getUpcomingReminders() {
    return this.request<any>('/dashboard/upcoming-reminders');
  }

  async getOverdueInvoices() {
    return this.request<any>('/dashboard/overdue-invoices');
  }

  // --- Customers ---
  async getCustomers(params?: { search?: string; page?: number; page_size?: number }) {
    const q = new URLSearchParams();
    if (params?.search) q.set('search', params.search);
    if (params?.page) q.set('page', params.page.toString());
    if (params?.page_size) q.set('page_size', params.page_size.toString());
    return this.request<any>(`/customers?${q.toString()}`);
  }

  async getCustomer(id: string) {
    return this.request<any>(`/customers/${id}`);
  }

  async createCustomer(data: { name: string; phone?: string; email?: string; external_ref?: string; notes?: string }) {
    return this.request<any>('/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async patchCustomer(id: string, data: Record<string, any>) {
    return this.request<any>(`/customers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteCustomer(id: string) {
    return this.request<any>(`/customers/${id}`, {
      method: 'DELETE',
    });
  }

  // --- Invoices ---
  async getInvoices(params?: { status?: string; customer_id?: string; overdue_only?: boolean; page?: number; page_size?: number }) {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.customer_id) q.set('customer_id', params.customer_id);
    if (params?.overdue_only) q.set('overdue_only', 'true');
    if (params?.page) q.set('page', params.page.toString());
    if (params?.page_size) q.set('page_size', params.page_size.toString());
    return this.request<any>(`/invoices?${q.toString()}`);
  }

  async getInvoice(id: string) {
    return this.request<any>(`/invoices/${id}`);
  }

  async createInvoice(data: { customer_id: string; number: string; total_paise: number; issued_on: string; due_on: string; description?: string }) {
    return this.request<any>('/invoices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async patchInvoice(id: string, data: Record<string, any>) {
    return this.request<any>(`/invoices/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async getInvoicePayments(invoiceId: string) {
    return this.request<any>(`/invoices/${invoiceId}/payments`);
  }

  async addPayment(invoiceId: string, data: { amount_paise: number; paid_on?: string; method: string; note?: string }) {
    return this.request<any>(`/invoices/${invoiceId}/payments`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // --- Reminders ---
  async getReminders(params?: { customer_id?: string; status?: string; channel?: string; page?: number; page_size?: number }) {
    const q = new URLSearchParams();
    if (params?.customer_id) q.set('customer_id', params.customer_id);
    if (params?.status) q.set('status', params.status);
    if (params?.channel) q.set('channel', params.channel);
    if (params?.page) q.set('page', params.page.toString());
    if (params?.page_size) q.set('page_size', params.page_size.toString());
    return this.request<any>(`/reminders?${q.toString()}`);
  }

  async createReminder(data: { customer_id: string; invoice_id?: string; scheduled_at: string; channel: string }) {
    return this.request<any>('/reminders', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async cancelReminder(id: string) {
    return this.request<any>(`/reminders/${id}/cancel`, {
      method: 'POST',
    });
  }

  async completeReminder(id: string) {
    return this.request<any>(`/reminders/${id}/complete`, {
      method: 'POST',
    });
  }

  // --- Payment Commitments ---
  async getCommitments(params?: { customer_id?: string; status?: string; page?: number; page_size?: number }) {
    const q = new URLSearchParams();
    if (params?.customer_id) q.set('customer_id', params.customer_id);
    if (params?.status) q.set('status', params.status);
    if (params?.page) q.set('page', params.page.toString());
    if (params?.page_size) q.set('page_size', params.page_size.toString());
    return this.request<any>(`/payment-commitments?${q.toString()}`);
  }

  async createCommitment(data: { customer_id: string; invoice_id?: string; promised_amount_paise?: number; promised_on: string }) {
    return this.request<any>('/payment-commitments', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async patchCommitment(id: string, data: Record<string, any>) {
    return this.request<any>(`/payment-commitments/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // --- Assistant / AI Conversations ---
  async getConversations() {
    return this.request<any>('/conversations');
  }

  async createConversation(data?: { agent_id?: string; title?: string; language?: Language }) {
    return this.request<any>('/conversations', {
      method: 'POST',
      body: JSON.stringify(data || {}),
    });
  }

  async getConversationMessages(conversationId: string) {
    return this.request<any>(`/conversations/${conversationId}/messages`);
  }

  async sendMessage(conversationId: string, content: string, language?: Language) {
    return this.request<any>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, language }),
    });
  }

  async sendAudioMessage(conversationId: string, audioBlob: Blob, language?: Language, includeSpeech: boolean = true) {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');
    if (language) formData.append('language', language);
    if (includeSpeech) formData.append('include_speech', 'true');

    return this.request<any>(`/conversations/${conversationId}/messages/audio`, {
      method: 'POST',
      body: formData,
    });
  }

  // --- Actions ---
  async getActions(status?: string) {
    const q = status ? `?status=${status}` : '';
    return this.request<any>(`/actions${q}`);
  }

  async confirmAction(actionId: string) {
    return this.request<any>(`/actions/${actionId}/confirm`, {
      method: 'POST',
    });
  }

  async cancelAction(actionId: string) {
    return this.request<any>(`/actions/${actionId}/cancel`, {
      method: 'POST',
    });
  }

  // --- Agents ---
  async getAgents() {
    return this.request<any>('/agents');
  }

  async generateAgent(description: string, language?: Language) {
    return this.request<any>('/agents/generate', {
      method: 'POST',
      body: JSON.stringify({ description, language }),
    });
  }

  async createAgent(data: any) {
    return this.request<any>('/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async patchAgent(agentId: string, data: any) {
    return this.request<any>(`/agents/${agentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async testAgent(agentId: string, message: string, language?: Language) {
    return this.request<any>(`/agents/${agentId}/test`, {
      method: 'POST',
      body: JSON.stringify({ message, language }),
    });
  }

  async activateAgent(agentId: string) {
    return this.request<any>(`/agents/${agentId}/activate`, {
      method: 'POST',
    });
  }

  async deactivateAgent(agentId: string) {
    return this.request<any>(`/agents/${agentId}/deactivate`, {
      method: 'POST',
    });
  }

  // --- Audio Studio ---
  async transcribeAudio(audioBlob: Blob, languageHint?: Language) {
    const formData = new FormData();
    formData.append('file', audioBlob, 'audio.webm');
    if (languageHint) formData.append('language_hint', languageHint);
    return this.request<any>('/audio/transcribe', {
      method: 'POST',
      body: formData,
    });
  }

  async generateSpeech(text: string, language: Language = 'hi-Latn', voice?: string) {
    return this.request<any>('/audio/speech', {
      method: 'POST',
      body: JSON.stringify({ text, language, voice }),
    });
  }

  async getAudioProviders() {
    return this.request<any>('/audio/providers');
  }
}

export const api = new ApiClient();

