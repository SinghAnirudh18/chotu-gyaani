import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Customer, Invoice } from '../types';
import { formatINR, formatDate, rupeesToPaise } from '../utils/formatters';
import {
  FileText,
  Plus,
  CreditCard,
  Search,
  Filter,
  CheckCircle,
  AlertTriangle,
  X,
  Receipt,
  Calendar,
} from 'lucide-react';

export const Invoices: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  // Add Invoice Form
  const [customerId, setCustomerId] = useState('');
  const [number, setNumber] = useState('');
  const [amountRupees, setAmountRupees] = useState<string>('');
  const [issuedOn, setIssuedOn] = useState(new Date().toISOString().split('T')[0]);
  const [dueOn, setDueOn] = useState(
    new Date(Date.now() + 15 * 86400000).toISOString().split('T')[0]
  );
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Payment Form
  const [paymentRupees, setPaymentRupees] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('upi');
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split('T')[0]);
  const [paymentNote, setPaymentNote] = useState('');

  const fetchInvoices = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (statusFilter === 'overdue') {
        params.overdue_only = true;
      } else if (statusFilter !== 'all') {
        params.status = statusFilter;
      }
      const res = await api.getInvoices(params);
      setInvoices(res.data?.items || res.data || []);
    } catch (err) {
      console.error('Failed to load invoices', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCustomers = async () => {
    try {
      const res = await api.getCustomers();
      setCustomers(res.data?.items || res.data || []);
    } catch (err) {
      console.error('Failed to load customers', err);
    }
  };

  useEffect(() => {
    fetchInvoices();
    fetchCustomers();
  }, [statusFilter]);

  const handleCreateInvoice = async (e: React.FormEvent) => {
    e.preventDefault();
    const rupees = parseFloat(amountRupees);
    if (isNaN(rupees) || rupees <= 0) {
      alert('Please enter a valid amount');
      return;
    }

    setSubmitting(true);
    try {
      await api.createInvoice({
        customer_id: customerId,
        number,
        total_paise: rupeesToPaise(rupees),
        issued_on: issuedOn,
        due_on: dueOn,
        description: description || undefined,
      });
      setShowAddModal(false);
      fetchInvoices();
    } catch (err: any) {
      alert(`Create invoice failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInvoice) return;
    const rupees = parseFloat(paymentRupees);
    if (isNaN(rupees) || rupees <= 0) {
      alert('Please enter a valid payment amount');
      return;
    }

    setSubmitting(true);
    try {
      await api.addPayment(selectedInvoice.id, {
        amount_paise: rupeesToPaise(rupees),
        paid_on: paymentDate,
        method: paymentMethod,
        note: paymentNote || undefined,
      });
      setShowPaymentModal(false);
      fetchInvoices();
    } catch (err: any) {
      alert(`Record payment failed: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const openPaymentFor = (inv: Invoice) => {
    setSelectedInvoice(inv);
    setPaymentRupees((inv.balance_paise / 100).toString());
    setShowPaymentModal(true);
  };

  const customerMap = React.useMemo(() => {
    const map = new Map<string, string>();
    customers.forEach((c) => map.set(c.id, c.name));
    return map;
  }, [customers]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <FileText className="h-5 w-5 text-brand-400" />
            Invoices, Bills & Dues (बिल और बकाया)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Track customer balances, issue bills, and log UPI/Cash payments.
          </p>
        </div>

        <button
          onClick={() => {
            setNumber(`INV-${Math.floor(1000 + Math.random() * 9000)}`);
            setAmountRupees('');
            setDescription('');
            if (customers.length > 0) setCustomerId(customers[0].id);
            setShowAddModal(true);
          }}
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-amber-400 transition cursor-pointer"
        >
          <Plus className="h-4 w-4" />
          <span>Create Invoice (नया बिल)</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        {['all', 'open', 'overdue', 'paid', 'void'].map((st) => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition cursor-pointer ${
              statusFilter === st
                ? 'bg-brand-500/20 text-brand-400 font-semibold border border-brand-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            {st}
          </button>
        ))}
      </div>

      {/* Invoices Table */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/90 text-slate-400 font-semibold">
              <th className="p-3.5">Invoice #</th>
              <th className="p-3.5">Customer</th>
              <th className="p-3.5">Total Amount</th>
              <th className="p-3.5">Balance Due</th>
              <th className="p-3.5">Dates</th>
              <th className="p-3.5">Status</th>
              <th className="p-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {invoices.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-slate-500">
                  {loading ? 'Loading invoices...' : 'No invoices matching filter.'}
                </td>
              </tr>
            ) : (
              invoices.map((inv) => {
                const cName = customerMap.get(inv.customer_id) || 'Unknown Customer';
                return (
                  <tr key={inv.id} className="hover:bg-slate-800/40 transition">
                    <td className="p-3.5 font-bold text-slate-200">
                      <span className="font-mono">{inv.number}</span>
                      {inv.description && (
                        <p className="text-[11px] text-slate-500 font-normal truncate max-w-xs">
                          {inv.description}
                        </p>
                      )}
                    </td>
                    <td className="p-3.5 font-medium text-slate-300">{cName}</td>
                    <td className="p-3.5 font-semibold text-slate-200">
                      {formatINR(inv.total_paise)}
                    </td>
                    <td className="p-3.5 font-bold">
                      <span
                        className={
                          inv.balance_paise > 0
                            ? inv.is_overdue
                              ? 'text-rose-400'
                              : 'text-amber-400'
                            : 'text-emerald-400'
                        }
                      >
                        {formatINR(inv.balance_paise)}
                      </span>
                    </td>
                    <td className="p-3.5 text-slate-400 text-[11px]">
                      <div>Issued: {formatDate(inv.issued_on)}</div>
                      <div className={inv.is_overdue ? 'text-rose-400 font-medium' : ''}>
                        Due: {formatDate(inv.due_on)}
                      </div>
                    </td>
                    <td className="p-3.5">
                      {inv.is_overdue ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 text-rose-300 px-2 py-0.5 text-[10px] font-semibold">
                          <AlertTriangle className="h-3 w-3" />
                          Overdue
                        </span>
                      ) : inv.status === 'paid' ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/20 text-emerald-300 px-2 py-0.5 text-[10px] font-semibold">
                          <CheckCircle className="h-3 w-3" />
                          Paid
                        </span>
                      ) : (
                        <span className="rounded-full bg-amber-500/20 text-amber-300 px-2 py-0.5 text-[10px] font-semibold uppercase">
                          {inv.status}
                        </span>
                      )}
                    </td>
                    <td className="p-3.5 text-right">
                      {inv.balance_paise > 0 && inv.status !== 'void' ? (
                        <button
                          onClick={() => openPaymentFor(inv)}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30 border border-emerald-500/30 px-2.5 py-1 text-xs font-semibold transition cursor-pointer"
                        >
                          <CreditCard className="h-3.5 w-3.5" />
                          <span>Record Payment</span>
                        </button>
                      ) : (
                        <span className="text-slate-500 text-[11px]">-</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Create Invoice Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-slate-100">Create New Invoice (बिल बनाएं)</h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateInvoice} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Select Customer *</label>
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

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Invoice Number *</label>
                  <input
                    type="text"
                    required
                    value={number}
                    onChange={(e) => setNumber(e.target.value)}
                    placeholder="INV-1001"
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Total Amount (₹) *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={amountRupees}
                    onChange={(e) => setAmountRupees(e.target.value)}
                    placeholder="5000"
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Issued Date *</label>
                  <input
                    type="date"
                    required
                    value={issuedOn}
                    onChange={(e) => setIssuedOn(e.target.value)}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Due Date *</label>
                  <input
                    type="date"
                    required
                    value={dueOn}
                    onChange={(e) => setDueOn(e.target.value)}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Description / Goods Note</label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. Cotton fabric bulk delivery batch #4"
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
                  {submitting ? 'Creating...' : 'Create Invoice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Record Payment Modal */}
      {showPaymentModal && selectedInvoice && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div>
                <h3 className="text-sm font-bold text-slate-100">
                  Record Payment for {selectedInvoice.number}
                </h3>
                <p className="text-xs text-slate-400">
                  Current Balance: {formatINR(selectedInvoice.balance_paise)}
                </p>
              </div>
              <button
                onClick={() => setShowPaymentModal(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleAddPayment} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Payment Amount (₹) *</label>
                <input
                  type="number"
                  step="0.01"
                  required
                  value={paymentRupees}
                  onChange={(e) => setPaymentRupees(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Method *</label>
                  <select
                    value={paymentMethod}
                    onChange={(e) => setPaymentMethod(e.target.value)}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none cursor-pointer"
                  >
                    <option value="upi">UPI (GPay / PhonePe / Paytm)</option>
                    <option value="cash">Cash (नकद)</option>
                    <option value="bank_transfer">Bank Transfer (NEFT/IMPS)</option>
                    <option value="cheque">Cheque</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Payment Date *</label>
                  <input
                    type="date"
                    required
                    value={paymentDate}
                    onChange={(e) => setPaymentDate(e.target.value)}
                    className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Transaction Ref / Note</label>
                <input
                  type="text"
                  value={paymentNote}
                  onChange={(e) => setPaymentNote(e.target.value)}
                  placeholder="e.g. UPI Ref #49281928"
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className="rounded-xl border border-slate-800 px-4 py-2 font-medium text-slate-300 hover:bg-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 font-semibold text-white shadow-lg hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? 'Recording...' : 'Save Payment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

