import React, { useState, useEffect } from 'react';
import { 
  FileCode, 
  Download, 
  Play, 
  RefreshCw, 
  Layers, 
  ExternalLink,
  CheckCircle2,
  Copy,
  Check
} from 'lucide-react';
import { WorkflowSpec } from '../types';
import { listSpecs, exportStandaloneScript } from '../api';

interface SpecsViewProps {
  onSelectSpecForRun: (spec: WorkflowSpec) => void;
}

export default function SpecsView({ onSelectSpecForRun }: SpecsViewProps) {
  const [specs, setSpecs] = useState<WorkflowSpec[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [exportedScript, setExportedScript] = useState<{ specId: string; script: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchSpecs = async () => {
    setIsLoading(true);
    try {
      const data = await listSpecs();
      setSpecs(data);
    } catch (e) {
      console.error('Failed to load specs', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSpecs();
  }, []);

  const handleExport = async (id: string) => {
    try {
      const data = await exportStandaloneScript(id);
      setExportedScript({ specId: id, script: data.playwright_script });
    } catch (e) {
      alert('Failed to export script');
    }
  };

  const handleDownloadFile = (specId: string, script: string) => {
    const blob = new Blob([script], { type: 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `skill_${specId}.py`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex items-center justify-between">
        <div>
          <h2 className="text-base font-extrabold text-white">Saved Workflow Skills</h2>
          <p className="text-xs text-slate-400">
            Export standalone self-contained Playwright scripts or execute parameterized runs
          </p>
        </div>

        <button
          onClick={fetchSpecs}
          disabled={isLoading}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-800 text-slate-200 hover:text-white transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {specs.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-slate-800 rounded-2xl bg-slate-900/40">
          <Layers className="w-10 h-10 mx-auto text-slate-600 mb-3" />
          <p className="text-sm text-slate-400 font-medium">No saved skills found yet</p>
          <p className="text-xs text-slate-500 mt-1">
            Record a browser session and compile it with Gemma 4 to generate a resilient skill.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {specs.map((spec) => (
            <div
              key={spec.id}
              className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition flex flex-col justify-between space-y-4 shadow-sm"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold text-sm text-white">{spec.name}</h3>
                  <span className="px-2 py-0.5 rounded font-mono text-[10px] bg-slate-800 text-slate-400">
                    {spec.id}
                  </span>
                </div>
                <div className="text-xs text-slate-400 font-mono mt-1 truncate">
                  {spec.start_url}
                </div>

                <div className="flex items-center gap-3 mt-3 text-xs text-slate-400">
                  <span>{spec.steps?.length || 0} steps</span>
                  <span>•</span>
                  <span>{spec.variables?.length || 0} variables</span>
                  {spec.success?.visual && (
                    <>
                      <span>•</span>
                      <span className="text-emerald-400">Dual-layer verified</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                <button
                  onClick={() => onSelectSpecForRun(spec)}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  Run Skill
                </button>
                <button
                  onClick={() => handleExport(spec.id)}
                  className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold transition"
                  title="Export Playwright Python script"
                >
                  <FileCode className="w-3.5 h-3.5" />
                  Export .py
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      
      {exportedScript && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={() => setExportedScript(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                <FileCode className="w-4 h-4 text-indigo-400" />
                Standalone Playwright Python Script ({exportedScript.specId}.py)
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleCopy(exportedScript.script)}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 hover:text-white rounded bg-slate-800"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button
                  onClick={() => handleDownloadFile(exportedScript.specId, exportedScript.script)}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download
                </button>
                <button
                  onClick={() => setExportedScript(null)}
                  className="px-2.5 py-1 text-xs text-slate-400 hover:text-white rounded bg-slate-800"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto pt-4">
              <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-indigo-200 overflow-x-auto leading-relaxed">
                {exportedScript.script}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
