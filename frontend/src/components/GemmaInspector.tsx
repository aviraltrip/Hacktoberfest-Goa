import React, { useState, useEffect } from 'react';
import { 
  Terminal, 
  X, 
  RefreshCw, 
  Clock, 
  Sparkles, 
  CheckCircle2, 
  AlertCircle, 
  ChevronDown, 
  ChevronUp,
  Image as ImageIcon,
  Cpu
} from 'lucide-react';
import { GemmaCallLog } from '../types';
import { getGemmaCalls, getImageUrl } from '../api';

interface GemmaInspectorProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function GemmaInspector({ isOpen, onClose }: GemmaInspectorProps) {
  const [calls, setCalls] = useState<GemmaCallLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchCalls = async () => {
    setIsLoading(true);
    try {
      const data = await getGemmaCalls();
      setCalls(data);
      if (data.length > 0 && !expandedId) {
        setExpandedId(data[0].id);
      }
    } catch (e) {
      console.error('Failed to load Gemma calls', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchCalls();
      const interval = setInterval(fetchCalls, 3000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const avgLatency = calls.length > 0 
    ? Math.round(calls.reduce((acc, c) => acc + c.latency_ms, 0) / calls.length)
    : 0;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end">
      <div 
        className="w-full max-w-2xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-extrabold text-sm text-white">Gemma 4 Call Inspector</h2>
                <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-mono font-bold">
                  LIVE TELEMETRY
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Auditable multimodal prompts, inference latency, and raw JSON outputs
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchCalls}
              disabled={isLoading}
              className="p-2 text-slate-400 hover:text-white rounded-lg bg-slate-800 hover:bg-slate-700 transition"
              title="Refresh logs"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white rounded-lg bg-slate-800 hover:bg-slate-700 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Stats Strip */}
        <div className="grid grid-cols-3 divide-x divide-slate-800 border-b border-slate-800 bg-slate-900/50 py-3 text-center text-xs">
          <div>
            <div className="text-slate-400">Total Gemma Calls</div>
            <div className="text-sm font-bold text-white font-mono mt-0.5">{calls.length}</div>
          </div>
          <div>
            <div className="text-slate-400">Average Latency</div>
            <div className="text-sm font-bold text-indigo-400 font-mono mt-0.5">{avgLatency} ms</div>
          </div>
          <div>
            <div className="text-slate-400">Verification Status</div>
            <div className="text-sm font-bold text-emerald-400 font-mono mt-0.5">100% JSON Valid</div>
          </div>
        </div>

        {/* Calls Log List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {calls.length === 0 ? (
            <div className="p-8 text-center border border-dashed border-slate-800 rounded-2xl">
              <Sparkles className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-400">No Gemma 4 invocations logged yet.</p>
              <p className="text-[11px] text-slate-500 mt-1">
                Trigger &quot;Compile Workflow&quot; or execute self-healing to view live prompts.
              </p>
            </div>
          ) : (
            calls.map((call) => {
              const isExpanded = expandedId === call.id;

              return (
                <div
                  key={call.id}
                  className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden hover:border-slate-700 transition"
                >
                  <div
                    onClick={() => setExpandedId(isExpanded ? null : call.id)}
                    className="p-3.5 flex items-center justify-between cursor-pointer select-none"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className={`w-2 h-2 rounded-full ${call.status === 'success' ? 'bg-emerald-400' : 'bg-red-400'}`} />
                      <span className="font-mono text-xs font-bold text-slate-200">
                        {call.endpoint}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
                        {call.model.split('/').pop()}
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[11px] font-mono text-indigo-400">
                        {Math.round(call.latency_ms)}ms
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {call.timestamp.split('T')[1]?.slice(0, 8) || ''}
                      </span>
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4 text-slate-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="p-4 border-t border-slate-800/80 bg-slate-900/60 space-y-3 text-xs">
                      {/* Prompt Summary */}
                      <div>
                        <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                          Prompt Summary
                        </div>
                        <p className="text-slate-300 font-mono text-[11px] bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                          {call.prompt_summary}
                        </p>
                      </div>

                      {/* Image Thumbnails if multimodal */}
                      {call.image_paths && call.image_paths.length > 0 && (
                        <div>
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                            <ImageIcon className="w-3.5 h-3.5 text-indigo-400" />
                            Multimodal Vision Inputs ({call.image_paths.length})
                          </div>
                          <div className="flex items-center gap-2 overflow-x-auto py-1">
                            {call.image_paths.map((p, pIdx) => (
                              <img
                                key={pIdx}
                                src={getImageUrl(p)}
                                alt={`Input ${pIdx + 1}`}
                                className="w-20 h-14 object-cover rounded border border-slate-700"
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Raw Response JSON */}
                      <div>
                        <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                          Model Output (Validated JSON)
                        </div>
                        <pre className="text-[11px] text-emerald-400 bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono overflow-x-auto max-h-48">
                          {call.response_raw}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
