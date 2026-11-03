import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { Globe, Building, Shield, LogOut, User as UserIcon } from 'lucide-react';
import { Language } from '../../types';

export const Navbar: React.FC<{ pendingCount?: number }> = ({ pendingCount = 0 }) => {
  const { user, memberships, activeBusiness, switchBusiness, language, setLanguage, logout } = useAuth();

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-900/90 px-4 sm:px-6 backdrop-blur">
      {/* Left: Brand & Business Selector */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-brand-600 to-amber-500 font-bold text-white shadow-lg shadow-brand-500/20">
            छ
          </div>
          <div className="hidden sm:block">
            <h1 className="text-base font-bold text-slate-100 flex items-center gap-1.5 leading-none">
              Chotu-Gyani
              <span className="text-[10px] uppercase font-semibold tracking-wider bg-brand-500/20 text-brand-400 px-1.5 py-0.5 rounded">
                AI
              </span>
            </h1>
            <p className="text-[11px] text-slate-400 mt-0.5">Your business. Your language. Your AI.</p>
          </div>
        </div>

        {/* Business Switcher */}
        {memberships.length > 0 && (
          <div className="ml-4 flex items-center gap-1.5 bg-slate-800/80 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs">
            <Building className="h-3.5 w-3.5 text-brand-400" />
            <select
              value={activeBusiness?.business_id || ''}
              onChange={(e) => switchBusiness(e.target.value)}
              className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer"
            >
              {memberships.map((m) => (
                <option key={m.business_id} value={m.business_id} className="bg-slate-900 text-slate-100">
                  {m.business_name} ({m.role})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        {/* Language Switcher */}
        <div className="flex items-center gap-1 bg-slate-800/80 border border-slate-700/80 rounded-lg px-2 py-1 text-xs text-slate-300">
          <Globe className="h-3.5 w-3.5 text-brand-400" />
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value as Language)}
            className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer text-xs"
          >
            <option value="hi-Latn" className="bg-slate-900 text-slate-100">Hinglish</option>
            <option value="hi" className="bg-slate-900 text-slate-100">हिन्दी (Hindi)</option>
            <option value="en" className="bg-slate-900 text-slate-100">English</option>
          </select>
        </div>

        {/* User Pill & Role */}
        {user && (
          <div className="flex items-center gap-2">
            <div className="hidden md:flex flex-col text-right">
              <span className="text-xs font-semibold text-slate-200">{user.name}</span>
              <span className="text-[10px] text-brand-400 capitalize flex items-center justify-end gap-1">
                <Shield className="h-2.5 w-2.5" /> {activeBusiness?.role || 'member'}
              </span>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 border border-slate-700 text-slate-300">
              <UserIcon className="h-4 w-4" />
            </div>
            <button
              onClick={logout}
              title="Logout"
              className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-lg transition"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

