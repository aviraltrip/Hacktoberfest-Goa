import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Square, 
  Circle, 
  Clock, 
  CheckCircle2, 
  ExternalLink, 
  Image as ImageIcon,
  Code,
  Sparkles,
  ChevronRight,
  Monitor
} from 'lucide-react';
import { Step } from '../types';
import { startRecording, stopRecording, getImageUrl } from '../api';

interface RecordPanelProps {
  onRecordingComplete: (recordingId: string, steps: Step[]) => void;
  onSelectStepToView?: (step: Step) => void;
}

export default function RecordPanel({ onRecordingComplete, onSelectStepToView }: RecordPanelProps) {
  const [startUrl, setStartUrl] = useState('http://localhost:8080/');
  const [headed, setHeaded] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingId, setRecordingId] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const timerRef = useRef<any>(null);

  useEffect(() => {
    if (isRecording) {
      timerRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(timerRef.current);
      setElapsed(0);
    }
    return () => clearInterval(timerRef.current);
  }, [isRecording]);

  const handleStart = async () => {
    setIsLoading(true);
    setError(null);
    setSteps([]);
    try {
      const res = await startRecording(startUrl, headed);
      setRecordingId(res.recording_id);
      setIsRecording(true);

      // Connect to SSE stream
      const es = new EventSource(`/api/record/events?id=${res.recording_id}`);
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'step_recorded' || data.type === 'step') {
            const newStep = data.step || data;
            setSteps((prev) => [...prev, newStep]);
          }
        } catch (e) {
          console.error('Error parsing SSE event:', e);
        }
      };
      es.onerror = (e) => {
        console.warn('SSE stream closed or error:', e);
        es.close();
      };
      eventSourceRef.current = es;
    } catch (err: any) {
      let msg = err.message || 'Failed to start recording';
      if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg === 'Failed to start recording') {
        msg = 'Cannot connect to backend server. Please verify backend is running (python scripts/start_stack.py)';
      }
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStop = async () => {
    if (!recordingId) return;
    setIsLoading(true);
    try {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      const res = await stopRecording(recordingId);
      setIsRecording(false);
      onRecordingComplete(recordingId, res.steps || res.raw_steps || steps);
    } catch (err: any) {
      setError(err.message || 'Failed to stop recording');
    } finally {
      setIsLoading(false);
    }
  };

  const formatTimer = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6">
      {/* Top Controls Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="flex-1 space-y-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
              Target Web Application URL
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={startUrl}
                disabled={isRecording}
                onChange={(e) => setStartUrl(e.target.value)}
                placeholder="http://localhost:8080/"
                className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              />
              <button
                type="button"
                disabled={isRecording}
                onClick={() => setStartUrl('http://localhost:8000/demo/')}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-indigo-900/60 text-indigo-200 hover:text-white hover:bg-indigo-800 border border-indigo-700/50 transition"
                title="Embedded Demo in FastAPI"
              >
                Local /demo
              </button>
              <button
                type="button"
                disabled={isRecording}
                onClick={() => setStartUrl('http://localhost:8080/')}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
                title="ScholarshipPortal Baseline (:8080)"
              >
                :8080 V1
              </button>
              <button
                type="button"
                disabled={isRecording}
                onClick={() => setStartUrl('http://localhost:8080/?v=2')}
                className="px-3 py-2 text-xs font-medium rounded-lg bg-indigo-950 text-indigo-300 hover:text-white hover:bg-indigo-900 border border-indigo-800/50 transition"
                title="ScholarshipPortal Mutated"
              >
                V2 Mutated (?v=2)
              </button>
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2 lg:pt-6">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={headed}
                disabled={isRecording}
                onChange={(e) => setHeaded(e.target.checked)}
                className="w-4 h-4 rounded text-indigo-600 bg-slate-950 border-slate-700 focus:ring-indigo-500"
              />
              <span className="flex items-center gap-1.5">
                <Monitor className="w-3.5 h-3.5 text-slate-400" />
                Headed Browser
              </span>
            </label>

            {!isRecording ? (
              <button
                onClick={handleStart}
                disabled={isLoading}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50"
              >
                <Circle className="w-4 h-4 fill-red-500 text-red-500 animate-pulse" />
                Start Recording
              </button>
            ) : (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-red-950/60 border border-red-500/30 text-red-400 font-mono text-sm">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
                  <span>{formatTimer(elapsed)}</span>
                </div>
                <button
                  onClick={handleStop}
                  disabled={isLoading}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm bg-red-600 text-white hover:bg-red-500 shadow-lg shadow-red-600/30 transition-all disabled:opacity-50"
                >
                  <Square className="w-4 h-4 fill-current" />
                  Stop Recording
                </button>
              </div>
            )}
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-950/50 border border-red-800 text-red-300 text-xs">
            {error}
          </div>
        )}
      </div>

      {/* Recording Steps Feed */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <span>Captured Actions Feed</span>
            <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 text-xs">
              {steps.length} {steps.length === 1 ? 'step' : 'steps'}
            </span>
          </h3>
          {isRecording && (
            <span className="text-xs text-indigo-400 flex items-center gap-1.5 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              Recording live interactions...
            </span>
          )}
        </div>

        {steps.length === 0 ? (
          <div className="bg-slate-900/50 border border-dashed border-slate-800 rounded-2xl p-12 text-center">
            <Monitor className="w-10 h-10 mx-auto text-slate-600 mb-3" />
            <p className="text-sm text-slate-400 font-medium">No actions recorded yet</p>
            <p className="text-xs text-slate-500 mt-1">
              Click &quot;Start Recording&quot; to open Chromium and interact with the target form.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {steps.map((step, idx) => (
              <div
                key={step.idx || idx}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition group"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <span className="w-7 h-7 rounded-lg bg-slate-800 text-slate-300 text-xs font-mono font-bold flex items-center justify-center shrink-0">
                      {step.idx}
                    </span>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-mono font-bold uppercase tracking-wider ${
                          step.action === 'click' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                          step.action === 'fill' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                          step.action === 'select' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' :
                          step.action === 'goto' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                          'bg-slate-700 text-slate-300'
                        }`}>
                          {step.action}
                        </span>

                        {step.locators && step.locators[0] && (
                          <span className="text-xs font-mono text-slate-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                            {step.locators[0].kind}: {step.locators[0].value || step.locators[0].name}
                          </span>
                        )}

                        {step.value && (
                          <span className="text-xs font-mono text-indigo-300 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-800/40">
                            value=&quot;{step.value}&quot;
                          </span>
                        )}
                      </div>

                      {step.intent && (
                        <p className="text-xs text-slate-300 mt-2 font-medium flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                          {step.intent}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Thumbnail Previews */}
                  <div className="flex items-center gap-2 shrink-0">
                    {step.shot_before && (
                      <div className="relative group/thumb cursor-pointer">
                        <img
                          src={getImageUrl(step.shot_before)}
                          alt="Before"
                          className="w-16 h-10 object-cover rounded border border-slate-700 group-hover/thumb:border-indigo-500 transition"
                        />
                        <span className="absolute bottom-0.5 left-0.5 px-1 bg-black/80 text-[9px] text-slate-300 rounded">
                          Pre
                        </span>
                      </div>
                    )}
                    {step.shot_after && (
                      <div className="relative group/thumb cursor-pointer">
                        <img
                          src={getImageUrl(step.shot_after)}
                          alt="After"
                          className="w-16 h-10 object-cover rounded border border-slate-700 group-hover/thumb:border-indigo-500 transition"
                        />
                        <span className="absolute bottom-0.5 left-0.5 px-1 bg-black/80 text-[9px] text-slate-300 rounded">
                          Post
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
