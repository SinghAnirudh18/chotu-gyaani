import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Customer, Invoice, PaymentCommitment } from '../types';
import { formatDate, formatINR, rupeesToPaise } from '../utils/formatters';
import {
  Handshake,
  Plus,
  CheckCircle2,
  XCircle,
  AlertCircle,
  X,
  Calendar,
} from 'lucide-react';

export const Commitments: React.FC = () => {
  const [commitments, setCommitments] = useState<PaymentCommitment[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  // Modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [customerId, setCustomerId] = useState('');
  const [invoiceId, setInvoiceId] = useState('');
  const [amountRupees, setAmountRupees] = useState('');
  const [promisedOn, setPromisedOn] = useState(
    new Date(Date.now() + 7 * 86400000).toISOString().split('T')[0]
  );
  const [submitting, setSubmitting] = useState(false);

  const fetchCommitments = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      const res = await api.getCommitments(params);
      setCommitments(res.data?.items || res.data || []);
    } catch (err) {
      console.error('Failed to load commitments', err);
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
    fetchCommitments();
    fetchDependencies();
  }, [statusFilter]);

  const handleCreateCommitment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId || !promisedOn) return;

    setSubmitting(true);
    try {
      const rupees = amountRupees ? parseFloat(amountRupees) : null;
      await api.createCommitment({
        customer_id: customerId,
        invoice_id: invoiceId || undefined,
        promised_amount_paise: rupees ? rupeesToPaise(rupees) : undefined,
        promised_on: promisedOn,
      });
      setShowAddModal(false);
      fetchCommitments();
    } catch (err: any) {
      alert(`Record commitment failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const updateStatus = async (id: string, status: 'kept' | 'broken' | 'cancelled') => {
    try {
      await api.patchCommitment(id, { status });
      fetchCommitments();
    } catch (err: any) {
      alert(`Update status failed: ${err.message}`);
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

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Handshake className="h-5 w-5 text-emerald-400" />
            Payment Commitments & Promises (भुगतान का वादा)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Record customer verbal commitments to pay by a certain date without modifying ledger balance.
          </p>
        </div>

        <button
          onClick={() => {
            if (customers.length > 0) setCustomerId(customers[0].id);
            setAmountRupees('');
            setShowAddModal(true);
          }}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-amber-400 transition cursor-pointer"
        >
          <Plus className="h-4 w-4" />
          <span>Record Commitment (वादा दर्ज करें)</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        {['all', 'open', 'kept', 'broken', 'cancelled'].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition cursor-pointer ${
              statusFilter === st
                ? 'bg-emerald-500/20 text-emerald-400 font-semibold border border-emerald-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            {st}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/90 text-slate-400 font-semibold">
              <th className="p-3.5">Customer</th>
              <th className="p-3.5">Promised Amount</th>
              <th className="p-3.5">Linked Invoice</th>
              <th className="p-3.5">Promised Date</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {commitments.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-500">
                  {loading ? 'Loading commitments...' : 'No payment commitments found.'}
                </td>
              </tr>
            ) : (
              commitments.map((c) => {
                const cName = customerMap.get(c.customer_id) || 'Unknown Customer';
                const iNum = c.invoice_id ? invoiceMap.get(c.invoice_id) : '-';
                return (
                  <tr key={c.id} className="hover:bg-slate-800/40 transition">
                    <td className="p-3.5 font-bold text-slate-200">{cName}</td>
                    <td className="p-3.5 font-semibold text-emerald-400">
                      {c.promised_amount_paise ? formatINR(c.promised_amount_paise) : 'Full Balance'}
                    </td>
                    <td className="p-3.5 font-mono text-slate-400">{iNum}</td>
                    <td className="p-3.5 text-slate-300 font-medium">
                      {formatDate(c.promised_on)}
                    </td>
                    <td className="p-3.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          c.status === 'open'
                            ? 'bg-blue-500/20 text-blue-300'
                            : c.status === 'kept'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : c.status === 'broken'
                            ? 'bg-rose-500/20 text-rose-300'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {c.status}
                      </span>
                    </td>
                    <td className="p-3.5 text-right">
                      {c.status === 'open' ? (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => updateStatus(c.id, 'kept')}
                            title="Mark as Kept (Payment Received)"
                            className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-slate-800 rounded-lg transition cursor-pointer"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => updateStatus(c.id, 'broken')}
                            title="Mark as Broken"
                            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition cursor-pointer"
                          >
                            <AlertCircle className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => updateStatus(c.id, 'cancelled')}
                            title="Cancel Commitment"
                            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition cursor-pointer"
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

      {/* Record Commitment Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-slate-100">
                Record Payment Commitment (वादा दर्ज करें)
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCommitment} className="space-y-3.5 text-xs">
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
                      {c.name}
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
                  <option value="">-- General Commitment --</option>
                  {invoices.map((inv) => (
                    <option key={inv.id} value={inv.id}>
                      {inv.number} (Balance: ₹{(inv.balance_paise / 100).toFixed(0)})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  Promised Amount (₹) (Leave blank for full balance)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={amountRupees}
                  onChange={(e) => setAmountRupees(e.target.value)}
                  placeholder="e.g. 5000"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Promised Date *</label>
                <input
                  type="date"
                  required
                  value={promisedOn}
                  onChange={(e) => setPromisedOn(e.target.value)}
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
                  className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 font-semibold text-white shadow-lg hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? 'Saving...' : 'Record Commitment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

