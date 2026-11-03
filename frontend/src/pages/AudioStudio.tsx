import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { Language } from '../types';
import {
  Mic,
  MicOff,
  Volume2,
  Sparkles,
  Upload,
  Play,
  Pause,
  Layers,
  Radio,
  CheckCircle,
} from 'lucide-react';

export const AudioStudio: React.FC = () => {
  const [providers, setProviders] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'stt' | 'tts'>('stt');

  // STT state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [sttLanguage, setSttLanguage] = useState<Language>('hi-Latn');
  const [transcriptResult, setTranscriptResult] = useState<any>(null);
  const [sttLoading, setSttLoading] = useState(false);

  // TTS state
  const [ttsText, setTtsText] = useState('Namaste Sharma ji, aapka INV-1001 ka ₹10,000 ka payment overdue hai.');
  const [ttsLanguage, setTtsLanguage] = useState<Language>('hi-Latn');
  const [ttsVoice, setTtsVoice] = useState('troy');
  const [ttsAudioUrl, setTtsAudioUrl] = useState<string | null>(null);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<any>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    api.getAudioProviders().then((res) => {
      setProviders(res.data);
    }).catch(() => {});
  }, []);

  // STT recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach((t) => t.stop());
        await processStt(audioBlob);
      };

      mediaRecorder.start(250);
      setIsRecording(true);
      setRecordingDuration(0);
      timerRef.current = setInterval(() => {
        setRecordingDuration((p) => p + 1);
      }, 1000);
    } catch {
      alert('Microphone permission is required.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(timerRef.current);
    }
  };

  const processStt = async (blob: Blob) => {
    setSttLoading(true);
    setTranscriptResult(null);
    try {
      const res = await api.transcribeAudio(blob, sttLanguage);
      setTranscriptResult(res.data);
    } catch (err: any) {
      alert(`Transcription error: ${err.message}`);
    } finally {
      setSttLoading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processStt(file);
    }
  };

  // TTS generate
  const handleSynthesize = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ttsText.trim()) return;

    setTtsLoading(true);
    try {
      const res = await api.generateSpeech(ttsText, ttsLanguage, ttsVoice);
      const data = res.data;
      if (data.audio_base64) {
        const url = `data:${data.mime_type};base64,${data.audio_base64}`;
        setTtsAudioUrl(url);
        setIsPlaying(true);
      }
    } catch (err: any) {
      alert(`Synthesis error: ${err.message}`);
    } finally {
      setTtsLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Radio className="h-5 w-5 text-amber-400" />
            Voice & Multilingual Audio Lab
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Test Speech-to-Text transcription and Text-to-Speech synthesis in Indian business contexts.
          </p>
        </div>

        {/* Provider Indicators */}
        {providers && (
          <div className="flex items-center gap-2 text-xs">
            <span className="rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-1 text-slate-300">
              STT: <strong className="text-brand-400 uppercase font-mono">{providers.stt}</strong>
            </span>
            <span className="rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-1 text-slate-300">
              TTS: <strong className="text-amber-400 uppercase font-mono">{providers.tts}</strong>
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800">
        <button
          onClick={() => setActiveTab('stt')}
          className={`flex items-center gap-2 px-5 py-2.5 text-xs font-semibold border-b-2 transition cursor-pointer ${
            activeTab === 'stt'
              ? 'border-brand-500 text-brand-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Mic className="h-4 w-4" />
          <span>Speech to Text (बोलो और लिखो)</span>
        </button>
        <button
          onClick={() => setActiveTab('tts')}
          className={`flex items-center gap-2 px-5 py-2.5 text-xs font-semibold border-b-2 transition cursor-pointer ${
            activeTab === 'tts'
              ? 'border-amber-500 text-amber-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Volume2 className="h-4 w-4" />
          <span>Text to Speech (आवाज़ में सुनो)</span>
        </button>
      </div>

      {/* STT Panel */}
      {activeTab === 'stt' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow space-y-4">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Mic className="h-4 w-4 text-brand-400" />
              Audio Input & Recording
            </h3>

            <div className="flex items-center gap-3">
              <div className="flex-1">
                <label className="block text-slate-400 text-[11px] mb-1">Language Hint</label>
                <select
                  value={sttLanguage}
                  onChange={(e) => setSttLanguage(e.target.value as Language)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-100 focus:outline-none"
                >
                  <option value="hi-Latn">Hinglish (Roman Hindi)</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="en">English</option>
                </select>
              </div>
            </div>

            {/* Recording Controls */}
            <div className="flex flex-col items-center justify-center p-8 rounded-2xl border border-dashed border-slate-800 bg-slate-950/40 space-y-3">
              <button
                type="button"
                onClick={isRecording ? stopRecording : startRecording}
                className={`h-16 w-16 rounded-full flex items-center justify-center shadow-xl transition-all cursor-pointer ${
                  isRecording
                    ? 'bg-rose-500 text-white animate-pulse scale-110'
                    : 'bg-brand-500 text-white hover:bg-brand-600'
                }`}
              >
                {isRecording ? <MicOff className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
              </button>

              <span className="text-xs font-semibold text-slate-300">
                {isRecording ? `Recording... (${recordingDuration}s) - Click to Stop` : 'Click to Speak'}
              </span>

              <div className="flex items-center gap-2 pt-2">
                <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer border border-slate-800 px-3 py-1 rounded-lg bg-slate-900">
                  <Upload className="h-3.5 w-3.5" />
                  <span>Upload Audio File</span>
                  <input type="file" accept="audio/*" onChange={handleFileUpload} className="hidden" />
                </label>
              </div>
            </div>
          </div>

          {/* STT Output */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow space-y-4">
            <h3 className="text-sm font-bold text-slate-100">Transcription Result</h3>

            {sttLoading ? (
              <div className="flex h-48 items-center justify-center text-xs text-slate-400 animate-pulse">
                Transcribing audio with STT provider...
              </div>
            ) : transcriptResult ? (
              <div className="space-y-3">
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs font-medium text-slate-100 whitespace-pre-wrap leading-relaxed">
                  "{transcriptResult.text}"
                </div>

                <div className="grid grid-cols-3 gap-2 text-[11px]">
                  <div className="bg-slate-950/60 border border-slate-800 p-2 rounded-lg">
                    <span className="text-slate-500 block">Language</span>
                    <span className="font-semibold text-slate-200">{transcriptResult.language}</span>
                  </div>
                  <div className="bg-slate-950/60 border border-slate-800 p-2 rounded-lg">
                    <span className="text-slate-500 block">Confidence</span>
                    <span className="font-semibold text-emerald-400">
                      {(transcriptResult.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="bg-slate-950/60 border border-slate-800 p-2 rounded-lg">
                    <span className="text-slate-500 block">Provider</span>
                    <span className="font-mono text-slate-300">{transcriptResult.provider}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center text-xs text-slate-500">
                Speak or upload an audio clip to see the transcription.
              </div>
            )}
          </div>
        </div>
      )}

      {/* TTS Panel */}
      {activeTab === 'tts' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <form
            onSubmit={handleSynthesize}
            className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow space-y-4"
          >
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Volume2 className="h-4 w-4 text-amber-400" />
              Text to Speech Synthesizer
            </h3>

            <div>
              <label className="block text-slate-400 text-[11px] mb-1">Text to Speak</label>
              <textarea
                rows={4}
                required
                value={ttsText}
                onChange={(e) => setTtsText(e.target.value)}
                placeholder="Enter text in Hindi or English..."
                className="w-full rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-100 focus:border-amber-500 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block text-slate-400 text-[11px] mb-1">Language</label>
                <select
                  value={ttsLanguage}
                  onChange={(e) => setTtsLanguage(e.target.value as Language)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none"
                >
                  <option value="hi-Latn">Hinglish</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="en">English</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 text-[11px] mb-1">Voice Profile</label>
                <select
                  value={ttsVoice}
                  onChange={(e) => setTtsVoice(e.target.value)}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 focus:outline-none"
                >
                  <option value="troy">Troy (Default)</option>
                  <option value="priya">Priya (Indian)</option>
                  <option value="rajesh">Rajesh (Indian)</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={ttsLoading}
              className="w-full rounded-xl bg-gradient-to-r from-amber-500 to-brand-600 py-2.5 text-xs font-semibold text-white shadow-lg hover:from-amber-400 hover:to-brand-500 transition disabled:opacity-50 cursor-pointer"
            >
              {ttsLoading ? 'Synthesizing Audio...' : 'Generate Voice Audio'}
            </button>
          </form>

          {/* Audio Output Player */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow space-y-4">
            <h3 className="text-sm font-bold text-slate-100">Audio Playback</h3>

            {ttsAudioUrl ? (
              <div className="space-y-4">
                <audio
                  ref={audioPlayerRef}
                  src={ttsAudioUrl}
                  controls
                  autoPlay
                  className="w-full rounded-xl bg-slate-950"
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                />
                <div className="p-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-300 flex items-center gap-2">
                  <CheckCircle className="h-4 w-4" />
                  <span>Synthesized successfully. Ready for playback or download.</span>
                </div>
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center text-xs text-slate-500">
                Click "Generate Voice Audio" to preview synthetic speech.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

