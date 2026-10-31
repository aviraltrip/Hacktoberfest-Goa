import React, { useState } from 'react';
import { Sparkles, Terminal, Activity, Layers, Play, CheckCircle2 } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'record' | 'runs' | 'specs' | 'ablation'>('record');

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-30 px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-600/20 border border-indigo-500/30 rounded-xl text-indigo-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base tracking-tight text-white">DemoToSkill</span>
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Gemma 4 Native
              </span>
            </div>
            <p className="text-xs text-slate-400">Autonomous Self-Healing Web Skill Synthesizer</p>
          </div>
        </div>

        <nav className="flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('record')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'record' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Record & Synthesize
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'runs' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Batch Runs
          </button>
          <button
            onClick={() => setActiveTab('specs')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'specs' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Saved Skills
          </button>
          <button
            onClick={() => setActiveTab('ablation')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
              activeTab === 'ablation' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Ablation Benchmark
          </button>
        </nav>
      </header>

      <main className="flex-1 p-6 max-w-7xl w-full mx-auto">
        <div className="p-8 border border-dashed border-slate-800 rounded-2xl text-center">
          <p className="text-slate-400">DemoToSkill Dashboard Ready</p>
        </div>
      </main>
    </div>
  );
}
