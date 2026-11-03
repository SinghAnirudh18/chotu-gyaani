import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Settings as SettingsIcon, Users, User, Shield, Download, Mail, Plus } from 'lucide-react';
import { Language } from '../types';

export const Settings: React.FC = () => {
  const { user, activeBusiness, language, setLanguage, refreshUser } = useAuth();
  const [businessData, setBusinessData] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'admin' | 'member'>('member');
  const [inviting, setInviting] = useState(false);

  // User Profile form
  const [userName, setUserName] = useState(user?.name || '');
  const [savingUser, setSavingUser] = useState(false);

  useEffect(() => {
    api.getBusinessMe().then((res) => setBusinessData(res.data)).catch(() => {});
    api.getMembers().then((res) => setMembers(res.data || [])).catch(() => {});
  }, []);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingUser(true);
    try {
      await api.patchMe({ name: userName, preferred_language: language });
      await refreshUser();
      alert('Profile updated successfully!');
    } catch (err: any) {
      alert(`Update failed: ${err.message}`);
    } finally {
      setSavingUser(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail) return;
    setInviting(true);
    try {
      await api.inviteMember({ email: inviteEmail, role: inviteRole });
      setInviteEmail('');
      alert(`Invitation sent to ${inviteEmail}`);
      const res = await api.getMembers();
      setMembers(res.data || []);
    } catch (err: any) {
      alert(`Invite failed: ${err.message}`);
    } finally {
      setInviting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
          <SettingsIcon className="h-5 w-5 text-brand-400" />
          Business & Team Settings
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Manage business tenancy, user preferences, and role-based permissions.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Business Info */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow space-y-4">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Shield className="h-4 w-4 text-amber-400" />
            Active Business Tenancy
          </h3>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-500 block">Business Name</span>
              <span className="text-slate-200 font-semibold text-sm">
                {businessData?.name || activeBusiness?.business_name || 'Sharma Traders'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-slate-500 block">Timezone</span>
                <span className="text-slate-200 font-mono">
                  {businessData?.timezone || 'Asia/Kolkata'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Base Currency</span>
                <span className="text-slate-200 font-mono">
                  {businessData?.currency || 'INR (₹)'}
                </span>
              </div>
            </div>

            <div>
              <span className="text-slate-500 block">Tenant Isolation ID</span>
              <span className="text-slate-400 font-mono text-[10px] break-all">
                {activeBusiness?.business_id}
              </span>
            </div>
          </div>
        </div>

        {/* User Preferences */}
        <form
          onSubmit={handleUpdateProfile}
          className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow space-y-4"
        >
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <User className="h-4 w-4 text-brand-400" />
            Your Profile & Language
          </h3>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Full Name</label>
              <input
                type="text"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:border-brand-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Email Address</label>
              <input
                type="email"
                disabled
                value={user?.email || ''}
                className="w-full rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2 text-slate-400 cursor-not-allowed"
              />
            </div>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Preferred Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
                className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none"
              >
                <option value="hi-Latn">Hinglish (Roman Hindi)</option>
                <option value="hi">हिन्दी (Hindi)</option>
                <option value="en">English</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={savingUser}
              className="rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 px-4 py-2 font-semibold text-slate-200 transition cursor-pointer"
            >
              {savingUser ? 'Saving...' : 'Update Preferences'}
            </button>
          </div>
        </form>
      </div>

      {/* Team Members */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Users className="h-4 w-4 text-emerald-400" />
            Team Members & Roles
          </h3>
        </div>

        {/* Invite Form */}
        <form onSubmit={handleInvite} className="flex gap-2 text-xs">
          <input
            type="email"
            required
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            placeholder="Invite colleague by email..."
            className="flex-1 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
          />
          <select
            value={inviteRole}
            onChange={(e) => setInviteRole(e.target.value as any)}
            className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none cursor-pointer"
          >
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
          <button
            type="submit"
            disabled={inviting}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 px-4 py-2 font-semibold text-white shadow hover:from-brand-500 hover:to-amber-400 disabled:opacity-50 cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Invite</span>
          </button>
        </form>

        <div className="divide-y divide-slate-800/60 pt-2">
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center justify-between py-2 text-xs">
              <div>
                <span className="font-semibold text-slate-200">{m.user_name || m.user_email}</span>
                <p className="text-[11px] text-slate-500">{m.user_email}</p>
              </div>
              <span className="rounded bg-slate-800 border border-slate-700 px-2 py-0.5 text-[10px] uppercase font-mono text-slate-300">
                {m.role}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

