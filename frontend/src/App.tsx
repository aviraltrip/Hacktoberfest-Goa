import React, { useState } from 'react';
import { 
  Sparkles, 
  Terminal, 
  Layers, 
  Play, 
  BarChart3, 
  ExternalLink,
  Wrench,
  ShieldCheck,
  Cpu
} from 'lucide-react';
import { Step, WorkflowSpec, HealProposal } from './types';
import RecordPanel from './components/RecordPanel';
import StepEditor from './components/StepEditor';
import RunGrid from './components/RunGrid';
import HealModal from './components/HealModal';
import GemmaInspector from './components/GemmaInspector';
import AblationView from './components/AblationView';
import SpecsView from './components/SpecsView';

export default function App() {
  const [activeTab, setActiveTab] = useState<'record' | 'runs' | 'specs' | 'ablation'>('record');
  
  // Recording & Compilation State
  const [currentRecordingId, setCurrentRecordingId] = useState<string | null>(null);
  const [recordedSteps, setRecordedSteps] = useState<Step[] | null>(null);
  const [compiledSpec, setCompiledSpec] = useState<WorkflowSpec | null>(null);

  // Healing Modal State
  const [activeHeal, setActiveHeal] = useState<{ runId: string; proposal: HealProposal } | null>(null);

  // Gemma Inspector Slide-over Drawer
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const handleRecordingComplete = (recId: string, steps: Step[]) => {
    setCurrentRecordingId(recId);
    setRecordedSteps(steps);
  };

  const handleCompilationComplete = (spec: WorkflowSpec) => {
    setCompiledSpec(spec);
    setRecordedSteps(null);
    setCurrentRecordingId(null);
    setActiveTab('runs');
  };

  const handleSelectSpecForRun = (spec: WorkflowSpec) => {
    setCompiledSpec(spec);
    setActiveTab('runs');
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur sticky top-0 z-40 px-6 py-3.5 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-600/20 border border-indigo-500/30 rounded-2xl text-indigo-400 shadow-inner">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base tracking-tight text-white">DemoToSkill</span>
              <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/25">
                Gemma 4 Only
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Autonomous Self-Healing Web Skill Synthesizer
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="hidden md:flex items-center gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl">
          <button
            onClick={() => setActiveTab('record')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'record' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Record &amp; Synthesize
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'runs' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Batch Runs
          </button>
          <button
            onClick={() => setActiveTab('specs')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'specs' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Saved Skills
          </button>
          <button
            onClick={() => setActiveTab('ablation')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'ablation' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Ablation Benchmark
          </button>
        </nav>

        {/* Right Action: Gemma Inspector Drawer Toggle */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setInspectorOpen(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-indigo-950/70 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-900/80 hover:text-white shadow-sm transition"
          >
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Gemma Inspector</span>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto">
        {activeTab === 'record' && (
          !recordedSteps ? (
            <RecordPanel onRecordingComplete={handleRecordingComplete} />
          ) : (
            <StepEditor
              recordingId={currentRecordingId!}
              initialSteps={recordedSteps}
              onCompilationComplete={handleCompilationComplete}
              onCancel={() => setRecordedSteps(null)}
            />
          )
        )}

        {activeTab === 'runs' && (
          <RunGrid
            currentSpec={compiledSpec}
            onHealTriggered={(runId, proposal) => setActiveHeal({ runId, proposal })}
          />
        )}

        {activeTab === 'specs' && (
          <SpecsView onSelectSpecForRun={handleSelectSpecForRun} />
        )}

        {activeTab === 'ablation' && (
          <AblationView />
        )}
      </main>

      {/* Set-of-Marks Healing Review Modal */}
      {activeHeal && (
        <HealModal
          runId={activeHeal.runId}
          proposal={activeHeal.proposal}
          onClose={() => setActiveHeal(null)}
          onHealResolved={() => setActiveHeal(null)}
        />
      )}

      {/* Gemma 4 Call Inspector Slide-Over Drawer */}
      <GemmaInspector
        isOpen={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
      />
    </div>
  );
}
