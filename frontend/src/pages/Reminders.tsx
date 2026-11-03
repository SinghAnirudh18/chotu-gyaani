import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Customer, Invoice, Reminder } from '../types';
import { formatDateTime } from '../utils/formatters';
import {
  Clock,
  Plus,
  CheckCircle,
  XCircle,
  MessageCircle,
  PhoneCall,
  Mail,
  X,
  Bell,
  AlertCircle,
} from 'lucide-react';

export const Reminders: React.FC = () => {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  // Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [customerId, setCustomerId] = useState('');
  const [invoiceId, setInvoiceId] = useState('');
  const [channel, setChannel] = useState<'whatsapp' | 'sms' | 'call' | 'in_app'>('whatsapp');
  const [scheduledAt, setScheduledAt] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchReminders = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      const res = await api.getReminders(params);
      setReminders(res.data?.items || res.data || []);
    } catch (err) {
      console.error('Failed to load reminders', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchDependencies = async () => {
    try {
      const [cRes, iRes] = await Promise.all([api.getCustomers(), api.getInvoices()]);
      setCustomers(cRes.data?.items || cRes.data || []);
      setInvoices(iRes.data?.items || iRes.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchReminders();
    fetchDependencies();
  }, [statusFilter]);

  const handleCreateReminder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId || !scheduledAt) return;

    setSubmitting(true);
    try {
      await api.createReminder({
        customer_id: customerId,
        invoice_id: invoiceId || undefined,
        scheduled_at: new Date(scheduledAt).toISOString(),
        channel,
      });
      setShowAddModal(false);
      fetchReminders();
    } catch (err: any) {
      alert(`Schedule reminder failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await api.cancelReminder(id);
      fetchReminders();
    } catch (err: any) {
      alert(`Cancel failed: ${err.message}`);
    }
  };

  const handleComplete = async (id: string) => {
    try {
      await api.completeReminder(id);
      fetchReminders();
    } catch (err: any) {
      alert(`Complete failed: ${err.message}`);
    }
  };

  const customerMap = React.useMemo(() => {
    const map = new Map<string, string>();
    customers.forEach((c) => map.set(c.id, c.name));
    return map;
  }, [customers]);

  const invoiceMap = React.useMemo(() => {
    const map = new Map<string, string>();
    invoices.forEach((i) => map.set(i.id, i.number));
    return map;
  }, [invoices]);

  const channelIcon = (ch: string) => {
    switch (ch) {
      case 'whatsapp':
        return <MessageCircle className="h-3.5 w-3.5 text-emerald-400" />;
      case 'call':
        return <PhoneCall className="h-3.5 w-3.5 text-amber-400" />;
      case 'sms':
        return <Mail className="h-3.5 w-3.5 text-blue-400" />;
      default:
        return <Bell className="h-3.5 w-3.5 text-purple-400" />;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Clock className="h-5 w-5 text-amber-400" />
            Payment Reminders & Takaada (तकादा शेड्यूल)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Automated WhatsApp, SMS, and Call reminders for overdue customer payments.
          </p>
        </div>

        <button
          onClick={() => {
            if (customers.length > 0) setCustomerId(customers[0].id);
            const tomorrow = new Date(Date.now() + 86400000);
            tomorrow.setHours(10, 0, 0, 0);
            setScheduledAt(tomorrow.toISOString().slice(0, 16));
            setShowAddModal(true);
          }}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-amber-400 transition cursor-pointer"
        >
          <Plus className="h-4 w-4" />
          <span>Schedule Reminder (नया तकादा)</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        {['all', 'scheduled', 'due', 'delivered', 'completed', 'cancelled'].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition cursor-pointer ${
              statusFilter === st
                ? 'bg-amber-500/20 text-amber-400 font-semibold border border-amber-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            {st}
          </button>
        ))}
      </div>

      {/* Reminders Table */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/90 text-slate-400 font-semibold">
              <th className="p-3.5">Customer</th>
              <th className="p-3.5">Channel</th>
              <th className="p-3.5">Linked Invoice</th>
              <th className="p-3.5">Scheduled Time</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {reminders.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500">
                  {loading ? 'Loading reminders...' : 'No reminders found.'}
                </td>
              </tr>
            ) : (
              reminders.map((rem) => {
                const cName = customerMap.get(rem.customer_id) || 'Unknown Customer';
                const iNum = rem.invoice_id ? invoiceMap.get(rem.invoice_id) : '-';
                return (
                  <tr key={rem.id} className="hover:bg-slate-800/40 transition">
                    <td className="p-3.5 font-bold text-slate-200">{cName}</td>
                    <td className="p-3.5">
                      <span className="inline-flex items-center gap-1.5 capitalize font-medium text-slate-300">
                        {channelIcon(rem.channel)}
                        {rem.channel}
                      </span>
                    </td>
                    <td className="p-3.5 font-mono text-slate-400">{iNum}</td>
                    <td className="p-3.5 text-slate-300 font-medium">
                      {formatDateTime(rem.scheduled_at)}
                    </td>
                    <td className="p-3.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          rem.status === 'scheduled'
                            ? 'bg-blue-500/20 text-blue-300'
                            : rem.status === 'due'
                            ? 'bg-amber-500/20 text-amber-300'
                            : rem.status === 'delivered'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {rem.status}
                      </span>
                    </td>
                    <td className="p-3.5 text-right">
                      {rem.status === 'scheduled' || rem.status === 'due' ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => handleComplete(rem.id)}
                            title="Mark as Done"
                            className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-slate-800 rounded-lg transition cursor-pointer"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleCancel(rem.id)}
                            title="Cancel Reminder"
                            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition cursor-pointer"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-600 text-[11px]">-</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Schedule Reminder Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-slate-100">Schedule Reminder (तकादा शेड्यूल करें)</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateReminder} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Customer *</label>
                <select
                  required
                  value={customerId}
                  onChange={(e) => setCustomerId(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                >
                  <option value="">-- Choose Customer --</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.phone_e164 ? `(${c.phone_e164})` : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Invoice (Optional)</label>
                <select
                  value={invoiceId}
                  onChange={(e) => setInvoiceId(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                >
                  <option value="">-- None / General Reminder --</option>
                  {invoices.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.number} (Balance: ₹{(inv.balance_paise / 100).toFixed(0)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Notification Channel *</label>
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as any)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none cursor-pointer"
                >
                  <option value="whatsapp">WhatsApp Message</option>
                  <option value="sms">SMS</option>
                  <option value="call">Automated Voice Call</option>
                  <option value="in_app">In-App Notification</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Scheduled Date & Time *</label>
                <input
                  type="datetime-local"
                  required
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="rounded-xl border border-slate-800 px-4 py-2 font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 font-semibold text-white shadow-lg hover:from-brand-500 hover:to-amber-400 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? 'Scheduling...' : 'Set Reminder'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
