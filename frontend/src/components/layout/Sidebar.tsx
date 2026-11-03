import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  MessageSquare,
  LayoutDashboard,
  Users,
  FileText,
  Clock,
  Handshake,
  Bot,
  Mic,
  Settings,
  Sparkles,
} from 'lucide-react';

interface SidebarProps {
  pendingActionsCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({ pendingActionsCount = 0 }) => {
  const navItems = [
    {
      to: '/',
      label: 'AI Assistant',
      hint: 'Voice & Text AI',
      icon: MessageSquare,
      badge: pendingActionsCount > 0 ? `${pendingActionsCount} pending` : undefined,
      highlight: true,
    },
    {
      to: '/dashboard',
      label: 'Dashboard',
      hint: 'Vyapaar Summary',
      icon: LayoutDashboard,
    },
    {
      to: '/customers',
      label: 'Customers',
      hint: 'Directory & Balances',
      icon: Users,
    },
    {
      to: '/invoices',
      label: 'Invoices & Dues',
      hint: 'Bills & Payments',
      icon: FileText,
    },
    {
      to: '/reminders',
      label: 'Reminders',
      hint: 'Takaada Schedules',
      icon: Clock,
    },
    {
      to: '/commitments',
      label: 'Commitments',
      hint: 'Payment Vaada',
      icon: Handshake,
    },
    {
      to: '/agents',
      label: 'AI Agents',
      hint: 'Custom AI Personas',
      icon: Bot,
    },
    {
      to: '/audio',
      label: 'Audio Lab',
      hint: 'STT / TTS Workbench',
      icon: Mic,
    },
    {
      to: '/settings',
      label: 'Settings',
      hint: 'Business & Team',
      icon: Settings,
    },
  ];

  return (
    <aside className="w-64 flex-shrink-0 border-r border-slate-800 bg-slate-900/50 flex flex-col justify-between p-3 min-h-[calc(100vh-4rem)]">
      <div className="space-y-1">
        <div className="px-3 py-2 text-[10px] font-bold tracking-wider text-slate-500 uppercase">
          Menu
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `group flex items-center justify-between rounded-xl px-3 py-2.5 text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20 font-semibold'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`
              }
            >
              <div className="flex items-center gap-3 min-w-0">
                <Icon
                  className={`h-4 w-4 flex-shrink-0 transition-transform group-hover:scale-110 ${
                    item.highlight ? 'text-amber-400' : 'text-slate-400 group-hover:text-slate-200'
                  }`}
                />
                <div className="flex flex-col truncate">
                  <span className="truncate leading-snug">{item.label}</span>
                  <span className="text-[10px] text-slate-500 font-normal">{item.hint}</span>
                </div>
              </div>
              {item.badge && (
                <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300 animate-pulse">
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </div>

      {/* Bottom Tip Card */}
      <div className="rounded-xl border border-slate-800 bg-gradient-to-b from-slate-800/40 to-slate-900/60 p-3 text-xs text-slate-400 space-y-1">
        <div className="flex items-center gap-1.5 text-brand-400 font-semibold text-[11px]">
          <Sparkles className="h-3.5 w-3.5" />
          <span>Multilingual Voice Ready</span>
        </div>
        <p className="text-[11px] leading-relaxed text-slate-400">
          Speak in Hindi, English or Hinglish: <span className="text-slate-200 italic">"Ramesh ka balance kitna hai?"</span>
        </p>
      </div>
    </aside>
  );
};

