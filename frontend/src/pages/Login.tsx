import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Shield, ArrowRight, CheckCircle2 } from 'lucide-react';
import { Language } from '../types';

export const Login: React.FC = () => {
  const { login, register, language, setLanguage } = useAuth();
  const navigate = useNavigate();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        await register({ email, password, name, businessName, preferred_language: language });
      } else {
        await login(email, password);
      }
      navigate('/');
    } catch (err: any) {
      setError(err?.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = async () => {
    setEmail('owner@sharmatraders.example.com');
    setPassword('Demo12345');
    setError(null);
    setLoading(true);
    try {
      await login('owner@sharmatraders.example.com', 'Demo12345');
      navigate('/');
    } catch (err: any) {
      setError(err?.message || 'Demo login failed. Make sure backend and database are running.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      {/* Left Hero Section */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between border-r border-slate-800 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 p-12">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-tr from-brand-600 to-amber-500 font-extrabold text-2xl text-white shadow-xl shadow-brand-500/25">
            छ
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              Chotu-Gyani <span className="text-xs bg-brand-500/20 text-brand-400 font-semibold px-2 py-0.5 rounded">छोटू ज्ञानी</span>
            </h1>
            <p className="text-xs text-slate-400">Your business. Your language. Your AI.</p>
          </div>
        </div>

        <div className="space-y-6 max-w-md">
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-500/30 bg-brand-500/10 px-3 py-1 text-xs text-brand-300">
            <Sparkles className="h-3.5 w-3.5" />
            <span>AI Voice Assistant for Indian Businesses</span>
          </div>

          <h2 className="text-3xl font-extrabold leading-tight text-slate-100">
            Manage customers, invoices & takaada in your own language.
          </h2>

          <div className="space-y-3 text-sm text-slate-400">
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
              <span>Voice commands in Hindi, English, and Hinglish</span>
            </div>
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
              <span>Automatic pending action preview & confirmation safety</span>
            </div>
            <div className="flex items-center gap-2.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 flex-shrink-0" />
              <span>Ledger, invoices in paise & automated payment reminders</span>
            </div>
          </div>
        </div>

        <div className="text-xs text-slate-500">
          Chotu-Gyani Monolith Architecture • Strict Multi-Tenancy • Idempotent Actions
        </div>
      </div>

      {/* Right Form Section */}
      <div className="flex flex-1 flex-col justify-center px-6 py-12 lg:px-12">
        <div className="mx-auto w-full max-w-md space-y-6">
          {/* Mobile Header */}
          <div className="lg:hidden flex items-center gap-3 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-brand-600 to-amber-500 font-bold text-lg text-white">
              छ
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Chotu-Gyani</h1>
              <p className="text-xs text-slate-400">Your business. Your language. Your AI.</p>
            </div>
          </div>

          {/* Quick Demo Login Pill */}
          <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-transparent p-4">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold text-amber-300 flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-amber-400" />
                  Instant Demo Access (Sharma Traders)
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Explore pre-seeded customers, overdue invoices, and test assistant queries.
                </p>
              </div>
            </div>
            <button
              onClick={fillDemo}
              disabled={loading}
              className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-500 to-brand-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-brand-500/25 hover:from-amber-400 hover:to-brand-500 transition disabled:opacity-50 cursor-pointer"
            >
              <span>Login as Sharma Traders Owner</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-800">
            <button
              onClick={() => { setIsRegister(false); setError(null); }}
              className={`flex-1 pb-3 text-sm font-semibold transition border-b-2 cursor-pointer ${
                !isRegister ? 'border-brand-500 text-brand-400' : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setIsRegister(true); setError(null); }}
              className={`flex-1 pb-3 text-sm font-semibold transition border-b-2 cursor-pointer ${
                isRegister ? 'border-brand-500 text-brand-400' : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              Register New Business
            </button>
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">Your Full Name</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Rajesh Sharma"
                    className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">Business / Shop Name</label>
                  <input
                    type="text"
                    required
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    placeholder="e.g. Sharma Traders, Anirudh Enterprises"
                    className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
                  />
                </div>
              </>
            )}

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Email Address</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@business.example.com"
                className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
            </div>

            {isRegister && (
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">Preferred AI Language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value as Language)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-900/80 px-3.5 py-2.5 text-xs text-slate-100 focus:border-brand-500 focus:outline-none cursor-pointer"
                >
                  <option value="hi-Latn">Hinglish (Roman script Hindi)</option>
                  <option value="hi">हिन्दी (Devanagari Hindi)</option>
                  <option value="en">English</option>
                </select>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 py-2.5 text-xs font-semibold text-slate-100 transition shadow disabled:opacity-50 cursor-pointer"
            >
              {loading ? 'Processing...' : isRegister ? 'Create Account' : 'Sign In'}
            </button>
          </form>

          <div className="flex items-center justify-center gap-2 text-xs text-slate-500 pt-4">
            <Shield className="h-3.5 w-3.5" />
            <span>Encrypted with Argon2id & JWT Authentication</span>
          </div>
        </div>
      </div>
    </div>
  );
};
