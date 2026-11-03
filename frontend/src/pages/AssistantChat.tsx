import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useOutletContext } from 'react-router-dom';
import {
  Mic,
  MicOff,
  Send,
  Sparkles,
  Bot,
  User as UserIcon,
  CheckCircle,
  XCircle,
  AlertCircle,
  Volume2,
  Calendar,
  Clock,
  RefreshCw,
  Plus,
} from 'lucide-react';
import { Conversation, Language, Message, PendingAction } from '../types';
import { formatINR, formatDateTime, getLanguageLabel } from '../utils/formatters';

export const AssistantChat: React.FC = () => {
  const { language, activeBusiness } = useAuth();
  const outletCtx = useOutletContext<{ refreshPending?: () => void }>();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [pendingActions, setPendingActions] = useState<Record<string, PendingAction>>({});
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Load conversations when active business is available
  const loadConversations = async () => {
    try {
      const res = await api.getConversations();
      const list = res.data || [];
      setConversations(list);
      if (list.length > 0) {
        setActiveConversation(list[0]);
      } else {
        // Create initial conversation
        const created = await api.createConversation({ language });
        setConversations([created.data]);
        setActiveConversation(created.data);
      }
    } catch (err) {
      console.error('Failed to load conversations', err);
    }
  };

  useEffect(() => {
    if (activeBusiness?.business_id) {
      loadConversations();
      fetchPendingActions();
    }
  }, [activeBusiness?.business_id]);

  // Fetch messages when conversation changes
  useEffect(() => {
    if (activeConversation) {
      loadMessages(activeConversation.id);
    }
  }, [activeConversation]);

  const loadMessages = async (convId: string) => {
    try {
      const res = await api.getConversationMessages(convId);
      setMessages(res.data || []);
    } catch (err) {
      console.error('Failed to load messages', err);
    }
  };

  const fetchPendingActions = async () => {
    try {
      const res = await api.getActions('pending_confirmation');
      const map: Record<string, PendingAction> = {};
      (res.data || []).forEach((a: PendingAction) => {
        map[a.id] = a;
      });
      setPendingActions(map);
      outletCtx?.refreshPending?.();
    } catch {
      // ignore
    }
  };

  const handleCreateNewConversation = async () => {
    if (!activeBusiness?.business_id) {
      alert('Please wait for business workspace to finish loading.');
      return;
    }
    api.setBusinessId(activeBusiness.business_id);
    try {
      const res = await api.createConversation({ language, title: 'New Conversation' });
      setConversations([res.data, ...conversations]);
      setActiveConversation(res.data);
      setMessages([]);
    } catch (err: any) {
      alert(`Could not create conversation: ${err?.message}`);
    }
  };

  const getOrCreateConversation = async (): Promise<Conversation | null> => {
    if (activeConversation) return activeConversation;
    if (!activeBusiness?.business_id) {
      alert('Please wait for business workspace to finish loading.');
      return null;
    }
    api.setBusinessId(activeBusiness.business_id);
    try {
      const res = await api.createConversation({ language, title: 'Chat' });
      const created = res.data;
      setActiveConversation(created);
      setConversations((prev) => [created, ...prev]);
      return created;
    } catch (err: any) {
      alert(`Could not start conversation: ${err?.message}`);
      return null;
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || isLoading) return;

    setInputMessage('');
    setIsLoading(true);

    const conv = await getOrCreateConversation();
    if (!conv) {
      setIsLoading(false);
      return;
    }

    // Optimistic user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: conv.id,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const res = await api.sendMessage(conv.id, text, language);
      const data = res.data;

      // Add assistant response
      if (data.assistant_message) {
        setMessages((prev) => [...prev.filter((m) => m.id !== tempUserMsg.id), data.user_message, data.assistant_message]);
      } else {
        loadMessages(conv.id);
      }

      if (data.action) {
        setPendingActions((prev) => ({ ...prev, [data.action.id]: data.action }));
        outletCtx?.refreshPending?.();
      }
    } catch (err: any) {
      console.error('Send message failed', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          conversation_id: conv.id,
          role: 'assistant',
          content: `Error: ${err?.message || 'Unable to process request.'}`,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsLoading(false);
      fetchPendingActions();
    }
  };

  // Voice Recording handlers
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach((track) => track.stop());
        await handleSendAudio(audioBlob);
      };

      mediaRecorder.start(250);
      setIsRecording(true);
      setRecordingDuration(0);
      timerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      alert('Microphone access is required to use voice input.');
      console.error('Microphone error', err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(timerRef.current);
    }
  };

  const handleSendAudio = async (audioBlob: Blob) => {
    setIsLoading(true);

    const conv = await getOrCreateConversation();
    if (!conv) {
      setIsLoading(false);
      return;
    }

    try {
      const res = await api.sendAudioMessage(conv.id, audioBlob, language, true);
      const data = res.data;

      if (data.assistant_message) {
        setMessages((prev) => [...prev, data.user_message, data.assistant_message]);
      } else {
        loadMessages(conv.id);
      }

      if (data.action) {
        setPendingActions((prev) => ({ ...prev, [data.action.id]: data.action }));
        outletCtx?.refreshPending?.();
      }

      // Check if TTS speech was returned
      if (data.speech && data.speech.audio_base64) {
        const audioData = `data:${data.speech.mime_type};base64,${data.speech.audio_base64}`;
        const audio = new Audio(audioData);
        audio.play().catch(() => {});
      }
    } catch (err: any) {
      alert(err?.message || 'Audio message failed');
    } finally {
      setIsLoading(false);
      fetchPendingActions();
    }
  };

  // Confirm or cancel action
  const handleConfirmAction = async (actionId: string) => {
    setActionLoading(actionId);
    try {
      await api.confirmAction(actionId);
      await fetchPendingActions();
      outletCtx?.refreshPending?.();
      if (activeConversation) {
        loadMessages(activeConversation.id);
      }
    } catch (err: any) {
      alert(`Confirm failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelAction = async (actionId: string) => {
    setActionLoading(actionId);
    try {
      await api.cancelAction(actionId);
      await fetchPendingActions();
      outletCtx?.refreshPending?.();
      if (activeConversation) {
        loadMessages(activeConversation.id);
      }
    } catch (err: any) {
      alert(`Cancel failed: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const quickPrompts = [
    { label: 'Ramesh ka balance', prompt: 'Ramesh Gupta ka balance kitna hai?' },
    { label: 'Overdue invoices', prompt: 'List all overdue invoices' },
    { label: 'Schedule reminder', prompt: 'Ramesh Gupta ko kal subah 10 baje reminder set karo' },
    { label: 'Payment commitment', prompt: 'Ramesh Gupta ne agle somvar ko 5000 dene ka vaada kiya hai' },
  ];

  return (
    <div className="flex h-[calc(100vh-6.5rem)] gap-4">
      {/* Main Chat Panel */}
      <div className="flex flex-1 flex-col rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-2xl backdrop-blur">
        {/* Chat Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3 bg-slate-900/80">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-600 to-amber-500 text-white font-bold text-xs shadow-md shadow-brand-500/20">
              छ
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xs font-bold text-slate-100">Chotu-Gyani AI Assistant</h2>
                <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-full font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                  Live
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Mode: <span className="text-slate-200 font-medium">{getLanguageLabel(language)}</span> • Intent-Gated Write Safety
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCreateNewConversation}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 transition cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>New Chat</span>
            </button>
          </div>
        </div>

        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center p-6 space-y-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-brand-600 to-amber-500 text-white shadow-xl shadow-brand-500/25">
                <Sparkles className="h-8 w-8" />
              </div>
              <div className="max-w-md space-y-1.5">
                <h3 className="text-base font-bold text-slate-100">Namaste! How can Chotu help today?</h3>
                <p className="text-xs text-slate-400">
                  Ask about customer dues, search invoices, schedule reminders, or record payment promises. Every financial action will be previewed for confirmation.
                </p>
              </div>

              {/* Quick Prompts */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg pt-2">
                {quickPrompts.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(q.prompt)}
                    className="flex flex-col text-left p-2.5 rounded-xl border border-slate-800 bg-slate-800/40 hover:bg-slate-800/80 hover:border-brand-500/40 transition cursor-pointer group"
                  >
                    <span className="text-xs font-semibold text-slate-200 group-hover:text-brand-400">
                      {q.label}
                    </span>
                    <span className="text-[11px] text-slate-400 truncate mt-0.5">{q.prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => {
            const isUser = m.role === 'user';
            return (
              <div key={m.id} className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
                {!isUser && (
                  <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-600 to-amber-500 text-white font-bold text-[11px] shadow">
                    छ
                  </div>
                )}

                <div className={`flex flex-col max-w-[80%] space-y-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-xs leading-relaxed shadow-sm ${
                      isUser
                        ? 'bg-gradient-to-r from-brand-600 to-amber-600 text-white rounded-tr-sm'
                        : 'bg-slate-800/90 border border-slate-700/80 text-slate-100 rounded-tl-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  </div>

                  <div className="flex items-center gap-2 px-1 text-[10px] text-slate-500">
                    <span>{formatDateTime(m.created_at)}</span>
                    {m.intent?.type && (
                      <span className="bg-slate-800/80 text-slate-400 border border-slate-700/60 px-1.5 py-0.2 rounded font-mono">
                        {m.intent.type}
                      </span>
                    )}
                  </div>
                </div>

                {isUser && (
                  <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-slate-800 border border-slate-700 text-slate-300">
                    <UserIcon className="h-4 w-4" />
                  </div>
                )}
              </div>
            );
          })}

          {/* Pending Action Cards inside stream */}
          {Object.values(pendingActions).map((action) => (
            <div
              key={action.id}
              className="my-3 rounded-2xl border-2 border-amber-500/40 bg-gradient-to-br from-amber-500/10 via-slate-900 to-slate-900 p-4 shadow-xl"
            >
              <div className="flex items-center justify-between pb-2 border-b border-amber-500/20">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-amber-400 animate-pulse" />
                  <span className="text-xs font-bold text-amber-300 uppercase tracking-wide">
                    Action Requires Confirmation: {action.type.replace('_', ' ')}
                  </span>
                </div>
                <span className="text-[10px] text-amber-400/80 font-mono">
                  Expires: {new Date(action.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>

              {/* Action Preview */}
              <div className="py-3 text-xs space-y-1.5 text-slate-200">
                {(action.preview?.text || action.preview?.message) && (
                  <p className="font-semibold text-slate-100">{action.preview?.text || action.preview?.message}</p>
                )}
                <div className="grid grid-cols-2 gap-2 mt-2 bg-slate-950/40 rounded-xl p-2.5 border border-slate-800 text-[11px]">
                  {Object.entries((action.preview?.fields as Record<string, any>) || action.preview || {}).map(([k, v]) => {
                    if (k === 'text' || k === 'message' || k === 'fields' || v === null || v === undefined) return null;
                    if (typeof v === 'object') return null;
                    return (
                      <div key={k} className="flex flex-col">
                        <span className="text-slate-400 uppercase text-[9px] font-bold tracking-wider">
                          {k.replace(/_/g, ' ')}
                        </span>
                        <span className="text-slate-100 font-medium">
                          {typeof v === 'number' && k.includes('paise') ? formatINR(v) : String(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  onClick={() => handleCancelAction(action.id)}
                  disabled={actionLoading === action.id}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-3.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 hover:text-rose-400 transition cursor-pointer"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Cancel (रद्द करें)</span>
                </button>
                <button
                  onClick={() => handleConfirmAction(action.id)}
                  disabled={actionLoading === action.id}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-emerald-600/20 hover:from-emerald-500 hover:to-teal-500 transition cursor-pointer"
                >
                  <CheckCircle className="h-3.5 w-3.5" />
                  <span>{actionLoading === action.id ? 'Processing...' : 'Confirm (पुष्टि करें)'}</span>
                </button>
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-brand-500/20 text-brand-400">
                <Sparkles className="h-3.5 w-3.5 animate-spin" />
              </div>
              <span className="animate-pulse">Chotu is thinking & verifying intent...</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="border-t border-slate-800 bg-slate-900/90 p-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2"
          >
            {/* Audio Record Button */}
            <button
              type="button"
              onClick={isRecording ? stopRecording : startRecording}
              className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl transition cursor-pointer shadow-md ${
                isRecording
                  ? 'bg-rose-500 text-white animate-pulse'
                  : 'bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 hover:text-amber-400'
              }`}
              title={isRecording ? 'Click to finish speaking' : 'Click to speak in Hindi/English/Hinglish'}
            >
              {isRecording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>

            {isRecording ? (
              <div className="flex-1 flex items-center justify-between bg-rose-500/10 border border-rose-500/30 rounded-xl px-4 py-2 text-xs text-rose-300">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-rose-500 animate-ping" />
                  <span>Listening... Speak clearly ({recordingDuration}s)</span>
                </div>
                <button
                  type="button"
                  onClick={stopRecording}
                  className="font-bold underline hover:text-rose-200 cursor-pointer text-xs"
                >
                  Send Recording
                </button>
              </div>
            ) : (
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                placeholder="Type or speak (e.g., 'Ramesh ka 5000 ka overdue invoice hai kya?')..."
                className="flex-1 rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:border-brand-500 focus:outline-none"
              />
            )}

            <button
              type="submit"
              disabled={isLoading || !inputMessage.trim()}
              className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-r from-brand-600 to-amber-500 text-white shadow-lg shadow-brand-500/20 hover:from-brand-500 hover:to-amber-400 transition disabled:opacity-40 cursor-pointer"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

