import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { DashboardSummary, ActivityItem, Invoice, Reminder } from '../types';
import { formatINR, formatDate, timeAgo } from '../utils/formatters';
import {
  TrendingUp,
  AlertTriangle,
  Users,
  Clock,
  ArrowUpRight,
  Receipt,
  Sparkles,
  CheckCircle2,
  Calendar,
  AlertCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [overdueInvoices, setOverdueInvoices] = useState<Invoice[]>([]);
  const [upcomingReminders, setUpcomingReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const [sumRes, actRes, overRes, remRes] = await Promise.allSettled([
        api.getDashboardSummary(),
        api.getDashboardActivity(1, 10),
        api.getOverdueInvoices(),
        api.getUpcomingReminders(),
      ]);

      if (sumRes.status === 'fulfilled') setSummary(sumRes.value.data);
      if (actRes.status === 'fulfilled') setActivity(actRes.value.data?.items || actRes.value.data || []);
      if (overRes.status === 'fulfilled') setOverdueInvoices(overRes.value.data || []);
      if (remRes.status === 'fulfilled') setUpcomingReminders(remRes.value.data || []);
    } catch (err) {
      console.error('Failed to load dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Banner & Quick AI prompt */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-800/80 p-5 shadow-xl">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            Vyapaar Overview & Ledger Health
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time balance, dues, collected payments, and automated takaada.
          </p>
        </div>

        <Link
          to="/"
          className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-amber-400 transition"
        >
          <Sparkles className="h-4 w-4" />
          <span>Ask Chotu-Gyani</span>
        </Link>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Outstanding */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow backdrop-blur relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Total Outstanding</span>
            <div className="rounded-xl bg-amber-500/10 p-2 text-amber-400">
              <Receipt className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-extrabold text-slate-100">
            {formatINR(summary?.total_outstanding_paise)}
          </p>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="text-amber-400 font-semibold">{summary?.open_invoices_count ?? 0}</span> open invoices
          </div>
        </div>

        {/* Overdue Amount */}
        <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-5 shadow backdrop-blur relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-rose-300">Overdue Dues</span>
            <div className="rounded-xl bg-rose-500/20 p-2 text-rose-400">
              <AlertTriangle className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-extrabold text-rose-200">
            {formatINR(summary?.overdue_paise)}
          </p>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-rose-300/80">
            <span className="font-semibold text-rose-300">{summary?.overdue_invoices_count ?? 0}</span> overdue bills
          </div>
        </div>

        {/* Collected This Month */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow backdrop-blur">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Collected This Month</span>
            <div className="rounded-xl bg-emerald-500/10 p-2 text-emerald-400">
              <TrendingUp className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-extrabold text-emerald-400">
            {formatINR(summary?.collected_this_month_paise)}
          </p>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-emerald-400/80">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>Updated in real time</span>
          </div>
        </div>

        {/* Active Customers */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow backdrop-blur">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Active Customers</span>
            <div className="rounded-xl bg-brand-500/10 p-2 text-brand-400">
              <Users className="h-4 w-4" />
            </div>
          </div>
          <p className="mt-3 text-2xl font-extrabold text-slate-100">
            {summary?.customers_count ?? 0}
          </p>
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="text-brand-400 font-semibold">{summary?.upcoming_reminders_count ?? 0}</span> upcoming reminders
          </div>
        </div>
      </div>

      {/* Two Column Grid: Overdue Invoices & Upcoming Reminders */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Overdue Invoices */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-rose-400" />
              <h3 className="text-sm font-bold text-slate-100">Overdue Invoices</h3>
            </div>
            <Link to="/invoices" className="text-xs text-brand-400 hover:text-brand-300 font-medium">
              View all bills →
            </Link>
          </div>

          <div className="space-y-2.5">
            {overdueInvoices.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">No overdue invoices right now!</p>
            ) : (
              overdueInvoices.slice(0, 5).map((inv) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-slate-950/40 p-3 hover:border-slate-700 transition"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-200">{inv.number}</span>
                      <span className="rounded bg-rose-500/20 px-1.5 py-0.2 text-[10px] font-semibold text-rose-300">
                        Overdue
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Due on {formatDate(inv.due_on)}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-bold text-rose-300">
                      {formatINR(inv.balance_paise)}
                    </span>
                    <p className="text-[10px] text-slate-500">Balance due</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Upcoming Reminders (Takaada) */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-400" />
              <h3 className="text-sm font-bold text-slate-100">Upcoming Reminders (Takaada)</h3>
            </div>
            <Link to="/reminders" className="text-xs text-brand-400 hover:text-brand-300 font-medium">
              Manage schedule →
            </Link>
          </div>

          <div className="space-y-2.5">
            {upcomingReminders.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">No reminders scheduled for today.</p>
            ) : (
              upcomingReminders.slice(0, 5).map((rem) => (
                <div
                  key={rem.id}
                  className="flex items-center justify-between rounded-xl border border-slate-800/80 bg-slate-950/40 p-3 hover:border-slate-700 transition"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400">
                      <Calendar className="h-4 w-4" />
                    </div>
                    <div>
                      <span className="text-xs font-semibold text-slate-200 capitalize">
                        {rem.channel} reminder
                      </span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Scheduled: {new Date(rem.scheduled_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] font-medium text-slate-300 uppercase">
                    {rem.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Activity Log */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow">
        <h3 className="text-sm font-bold text-slate-100 mb-3">Audit & Activity Log</h3>
        <div className="space-y-2">
          {activity.length === 0 ? (
            <p className="text-xs text-slate-500 py-4 text-center">No recent business activity logged.</p>
          ) : (
            activity.slice(0, 6).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between text-xs py-2 border-b border-slate-800/60 last:border-0"
              >
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-brand-500" />
                  <span className="font-semibold text-slate-200">{item.action_type}</span>
                  <span className="text-slate-500">• {item.entity_type}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300 font-mono">
                    {item.outcome}
                  </span>
                  <span className="text-slate-500 text-[11px]">{timeAgo(item.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

