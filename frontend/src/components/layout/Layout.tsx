import React, { useEffect, useState } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Navbar } from './Navbar';
import { Sidebar } from './Sidebar';
import { api } from '../../api/client';

export const Layout: React.FC = () => {
  const { user, memberships, createNewBusiness, isLoading } = useAuth();
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [newBizName, setNewBizName] = useState('');
  const [creatingBiz, setCreatingBiz] = useState(false);

  const fetchPending = async () => {
    try {
      const res = await api.getActions('pending_confirmation');
      setPendingCount(res.data?.length || 0);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (user && memberships.length > 0) {
      fetchPending();
      const interval = setInterval(fetchPending, 15000);
      return () => clearInterval(interval);
    }
  }, [user, memberships]);

  const handleCreateBusiness = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBizName.trim()) return;
    setCreatingBiz(true);
    try {
      await createNewBusiness(newBizName.trim());
    } catch (err: any) {
      alert(`Could not create business: ${err?.message}`);
    } finally {
      setCreatingBiz(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-slate-950 text-slate-400">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          <p className="text-xs text-slate-400 font-medium tracking-wide">Loading Chotu-Gyani...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // If user has no business, show initial business creation dialog
  if (memberships.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
        <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl space-y-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-brand-600 to-amber-500 font-bold text-white shadow-lg">
              छ
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-100">Setup Your Business (व्यापार सेटअप)</h2>
              <p className="text-xs text-slate-400">Every account requires a business workspace.</p>
            </div>
          </div>

          <form onSubmit={handleCreateBusiness} className="space-y-4 pt-2">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Business / Shop Name *</label>
              <input
                type="text"
                required
                value={newBizName}
                onChange={(e) => setNewBizName(e.target.value)}
                placeholder="e.g. Sharma Traders, Anirudh Enterprises"
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={creatingBiz || !newBizName.trim()}
              className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 py-2.5 text-xs font-semibold text-white shadow-lg hover:from-brand-500 hover:to-amber-400 disabled:opacity-50 cursor-pointer"
            >
              {creatingBiz ? 'Setting up Workspace...' : 'Create Workspace & Start'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <Navbar pendingCount={pendingCount} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar pendingActionsCount={pendingCount} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-slate-950">
          <Outlet context={{ refreshPending: fetchPending }} />
        </main>
      </div>
    </div>
  );
};

