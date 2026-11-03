import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Agent, Language } from '../types';
import { formatDateTime, getLanguageLabel } from '../utils/formatters';
import {
  Bot,
  Sparkles,
  Plus,
  Play,
  CheckCircle,
  Power,
  Settings2,
  X,
  MessageSquare,
  Wrench,
  BookOpen,
} from 'lucide-react';

export const Agents: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activeTab, setActiveTab] = useState<'list' | 'generate' | 'create'>('list');
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  // Generate Agent state
  const [genPrompt, setGenPrompt] = useState(
    'A polite Hindi-speaking collections agent that reminds overdue clients softly and offers UPI payment link options.'
  );
  const [genLanguage, setGenLanguage] = useState<Language>('hi-Latn');
  const [generating, setGenerating] = useState(false);

  // Test sandbox state
  const [testMessage, setTestMessage] = useState('Kal kitna payment due hai?');
  const [testResult, setTestResult] = useState<any>(null);
  const [testing, setTesting] = useState(false);

  const fetchAgents = async () => {
    try {
      setLoading(true);
      const res = await api.getAgents();
      const list = res.data?.items || res.data || [];
      setAgents(list);
      if (list.length > 0 && !selectedAgent) {
        setSelectedAgent(list[0]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genPrompt.trim()) return;

    setGenerating(true);
    try {
      const res = await api.generateAgent(genPrompt, genLanguage);
      const generatedConfig = res.data;
      // Auto create agent with this generated config
      const created = await api.createAgent(generatedConfig);
      await fetchAgents();
      setSelectedAgent(created.data);
      setActiveTab('list');
    } catch (err: any) {
      alert(`Generation failed: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const toggleActivate = async (agent: Agent) => {
    try {
      if (agent.status === 'active') {
        await api.deactivateAgent(agent.id);
      } else {
        await api.activateAgent(agent.id);
      }
      fetchAgents();
    } catch (err: any) {
      alert(`Status update failed: ${err.message}`);
    }
  };

  const runTest = async () => {
    if (!selectedAgent || !testMessage.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testAgent(selectedAgent.id, testMessage, selectedAgent.language);
      setTestResult(res.data);
    } catch (err: any) {
      setTestResult({ error: err.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Bot className="h-5 w-5 text-gyani-500" />
            AI Agents Studio (कस्टम एजेंट स्टूडियो)
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Create, tune, and test specialized AI personas with custom tools and business instructions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('generate')}
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-gyani-600 to-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-500/20 hover:from-gyani-500 hover:to-indigo-500 transition cursor-pointer"
          >
            <Sparkles className="h-4 w-4" />
            <span>Generate Agent with AI</span>
          </button>
        </div>
      </div>

      {activeTab === 'generate' && (
        <div className="rounded-2xl border border-indigo-500/30 bg-gradient-to-br from-indigo-500/10 via-slate-900 to-slate-900 p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-indigo-400" />
              <h3 className="text-sm font-bold text-slate-100">AI Prompt to Agent Builder</h3>
            </div>
            <button
              onClick={() => setActiveTab('list')}
              className="text-slate-400 hover:text-slate-200 cursor-pointer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <form onSubmit={handleGenerate} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">
                Describe the role, behavior and purpose of your Agent:
              </label>
              <textarea
                rows={4}
                required
                value={genPrompt}
                onChange={(e) => setGenPrompt(e.target.value)}
                placeholder="e.g. An assistant for Delhi textile wholesalers that answers payment inquiries, provides invoice breakdowns, and speaks polite Hinglish."
                className="w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <label className="block text-slate-400 text-[11px] mb-1">Target Language</label>
                <select
                  value={genLanguage}
                  onChange={(e) => setGenLanguage(e.target.value as Language)}
                  className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-slate-100 focus:outline-none"
                >
                  <option value="hi-Latn">Hinglish</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="en">English</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={generating}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-gyani-600 px-5 py-2 font-semibold text-white shadow-lg hover:from-indigo-500 hover:to-gyani-500 disabled:opacity-50 cursor-pointer"
              >
                <Sparkles className="h-4 w-4" />
                <span>{generating ? 'Crafting Agent with LLM...' : 'Generate & Activate'}</span>
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main Studio Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Agents List */}
        <div className="lg:col-span-1 space-y-3">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Your Configured Agents ({agents.length})
          </h3>
          <div className="space-y-2">
            {agents.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center">No custom agents configured.</p>
            ) : (
              agents.map((ag) => (
                <div
                  key={ag.id}
                  onClick={() => setSelectedAgent(ag)}
                  className={`p-3.5 rounded-xl border transition cursor-pointer ${
                    selectedAgent?.id === ag.id
                      ? 'border-indigo-500/50 bg-indigo-500/10 shadow-md'
                      : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-200">{ag.name}</span>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${
                        ag.status === 'active'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {ag.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                    {ag.description || 'No description provided.'}
                  </p>
                  <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                    <span>Language: {getLanguageLabel(ag.language)}</span>
                    <span>Tools: {ag.enabled_tools?.length || 0}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Selected Agent Details & Testing Sandbox */}
        <div className="lg:col-span-2 space-y-4">
          {selectedAgent ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow space-y-5">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div>
                  <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                    {selectedAgent.name}
                    <span className="text-[11px] font-normal text-slate-400">
                      v{selectedAgent.config_version}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">{selectedAgent.description}</p>
                </div>

                <button
                  onClick={() => toggleActivate(selectedAgent)}
                  className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition cursor-pointer ${
                    selectedAgent.status === 'active'
                      ? 'bg-slate-800 text-slate-300 hover:text-rose-400 border border-slate-700'
                      : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-md shadow-emerald-600/20'
                  }`}
                >
                  <Power className="h-3.5 w-3.5" />
                  <span>{selectedAgent.status === 'active' ? 'Deactivate' : 'Activate'}</span>
                </button>
              </div>

              {/* Tools and Instructions */}
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    System Instructions:
                  </label>
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-slate-300 whitespace-pre-wrap max-h-36 overflow-y-auto leading-relaxed">
                    {selectedAgent.instructions || 'Standard business assistant instructions apply.'}
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Enabled Tools ({selectedAgent.enabled_tools?.length || 0}):
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedAgent.enabled_tools?.map((tool) => (
                      <span
                        key={tool}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2 py-1 text-[11px] font-mono text-indigo-300"
                      >
                        <Wrench className="h-3 w-3" />
                        {tool}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Sandbox Tester */}
              <div className="pt-4 border-t border-slate-800 space-y-3">
                <div className="flex items-center gap-2">
                  <Play className="h-4 w-4 text-emerald-400" />
                  <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                    Interactive Sandbox Test (एजेंट का टेस्ट लें)
                  </h4>
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={testMessage}
                    onChange={(e) => setTestMessage(e.target.value)}
                    placeholder="Enter a test prompt in Hindi/English/Hinglish..."
                    className="flex-1 rounded-xl border border-slate-800 bg-slate-950 px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                  />
                  <button
                    onClick={runTest}
                    disabled={testing}
                    className="rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-2 text-xs font-semibold text-white shadow-md hover:from-emerald-500 hover:to-teal-500 transition disabled:opacity-50 cursor-pointer"
                  >
                    {testing ? 'Testing...' : 'Send Test'}
                  </button>
                </div>

                {testResult && (
                  <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between text-slate-400 text-[10px]">
                      <span>Outcome Preview</span>
                      <span className="font-mono text-emerald-400">
                        {testResult.tool ? `Tool: ${testResult.tool}` : 'Direct Reply'}
                      </span>
                    </div>
                    <p className="text-slate-200 font-medium whitespace-pre-wrap">
                      {testResult.reply || testResult.content || JSON.stringify(testResult, null, 2)}
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-800 text-slate-500 text-xs">
              Select an agent from the list or generate one with AI.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

