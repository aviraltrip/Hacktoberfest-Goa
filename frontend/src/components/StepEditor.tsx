import React, { useState, useRef, useEffect } from 'react';
import { 
  Sparkles, 
  Check, 
  Tag, 
  Eye, 
  AlertCircle 
} from 'lucide-react';
import { Step, Variable, WorkflowSpec } from '../types';
import { startCompilation, approveCompilation, getCompilation, getImageUrl } from '../api';

interface StepEditorProps {
  recordingId: string;
  initialSteps: Step[];
  onCompilationComplete: (spec: WorkflowSpec) => void;
  onCancel: () => void;
}

export default function StepEditor({
  recordingId,
  initialSteps,
  onCompilationComplete,
  onCancel
}: StepEditorProps) {
  const [workflowName, setWorkflowName] = useState('Scholarship Application Skill');
  const [steps, setSteps] = useState<Step[]>(initialSteps);
  const [isCompiling, setIsCompiling] = useState(false);
  const [compileElapsed, setCompileElapsed] = useState(0);
  const [compileStatus, setCompileStatus] = useState<string | null>(null);

  React.useEffect(() => {
    let timer: any = null;
    if (isCompiling) {
      setCompileElapsed(0);
      timer = setInterval(() => {
        setCompileElapsed(prev => prev + 1);
      }, 1000);
    } else {
      setCompileElapsed(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isCompiling]);
  const [compileId, setCompileId] = useState<string | null>(null);
  const compileIdRef = useRef<string | null>(null);
  const detectedVariablesRef = useRef<Variable[]>([]);
  const [reviewRequired, setReviewRequired] = useState(false);
  const [selectedShot, setSelectedShot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isCompiling || !compileId) return;

    let isDone = false;

    const processInterrupt = (payload: any) => {
      isDone = true;
      setReviewRequired(true);
      setIsCompiling(false);
      setCompileStatus('Gemma 4 parameter proposal ready for your confirmation.');
      if (payload?.variables) {
        detectedVariablesRef.current = payload.variables;
      }
      if (payload?.steps) {
        setSteps(payload.steps);
      }
      if (payload?.spec_name) {
        setWorkflowName(payload.spec_name);
      }
    };

    const processComplete = (spec: any) => {
      isDone = true;
      setCompileStatus('Compilation & verification complete!');
      setIsCompiling(false);
      if (spec) {
        onCompilationComplete(spec);
      }
    };

    const handleData = (dataStr: string) => {
      try {
        const data = JSON.parse(dataStr);
        const isInterrupt = 
          data.type === 'interrupt' || 
          data.type === 'interrupt_review_intents' || 
          data.interrupt_type === 'interrupt_review_intents' || 
          data.node === 'review_intents' ||
          data.status === 'review_pending';

        if (isInterrupt) {
          processInterrupt(data.payload || data.spec || {});
        } else if (data.status === 'saved' || data.type === 'compile_completed' || data.status === 'completed') {
          processComplete(data.spec);
        } else if (data.type === 'node_update' || data.type === 'node_start') {
          setCompileStatus(`LangGraph running node: ${data.node}...`);
        } else if (data.type === 'compile_error') {
          isDone = true;
          setError(data.error || 'Compilation failed');
          setIsCompiling(false);
        }
      } catch (e) {
        console.error('Error parsing compile event:', e);
      }
    };

    const es = new EventSource(`/api/compile/${compileId}/events`);
    es.onmessage = (event) => handleData(event.data);
    es.onerror = () => {
      es.close();
    };

    const pollTimer = setInterval(async () => {
      if (isDone) return;
      try {
        const statusRes = await getCompilation(compileId);
        if (statusRes.status === 'review_pending') {
          processInterrupt(statusRes.payload || statusRes.spec || {});
        } else if (statusRes.status === 'completed') {
          processComplete(statusRes.payload || statusRes.spec);
        } else if (statusRes.status === 'failed') {
          isDone = true;
          setError(statusRes.error || 'Compilation failed');
          setIsCompiling(false);
        }
      } catch (err) {
        // network retry
      }
    }, 1200);

    return () => {
      isDone = true;
      es.close();
      clearInterval(pollTimer);
    };
  }, [isCompiling, compileId, onCompilationComplete]);

  const handleStepIntentChange = (idx: number, newIntent: string) => {
    setSteps(prev => prev.map(s => s.idx === idx ? { ...s, intent: newIntent } : s));
  };

  const handleToggleVariable = (idx: number) => {
    setSteps(prev => prev.map(s => {
      if (s.idx !== idx) return s;
      const newRole = s.role === 'variable' ? 'constant' : 'variable';
      const defaultVarName = s.variable_name || `var_step_${s.idx}`;
      return {
        ...s,
        role: newRole,
        variable_name: newRole === 'variable' ? defaultVarName : null,
        value: newRole === 'variable' ? `{{${defaultVarName}}}` : s.value
      };
    }));
  };

  const handleVariableNameChange = (idx: number, newName: string) => {
    const cleaned = newName.replace(/[{}]/g, '').trim();
    setSteps(prev => prev.map(s => {
      if (s.idx !== idx) return s;
      return {
        ...s,
        variable_name: cleaned,
        value: `{{${cleaned}}}`
      };
    }));
  };

  const handleStartCompile = async () => {
    setIsCompiling(true);
    setError(null);
    setCompileStatus('Analyzing step intents with Gemma 4...');

    try {
      const res = await startCompilation(recordingId);
      compileIdRef.current = res.compile_id;
      setCompileId(res.compile_id);
    } catch (err: any) {
      setError(err.message || 'Compilation failed to start');
      setIsCompiling(false);
    }
  };

  const handleApproveAndSave = async () => {
    const activeCmpId = compileIdRef.current;
    if (!activeCmpId) return;
    setIsCompiling(true);
    setCompileStatus('Executing trial run and dual-layer verification...');

    try {
      await approveCompilation(activeCmpId, {
        name: workflowName,
        variables: detectedVariablesRef.current,
        steps: steps
      });
    } catch (err: any) {
      setError(err.message || 'Failed to approve compilation');
      setIsCompiling(false);
    }
  };

  return (
    <div className="space-y-6">
      
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex-1 space-y-1">
            <label htmlFor="workflow-skill-name-input" className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Workflow Skill Name
            </label>
            <input
              type="text"
              id="workflow-skill-name-input"
              aria-label="Workflow Skill Name"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2 text-base font-bold text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              disabled={isCompiling}
              className="px-4 py-2.5 rounded-xl text-xs font-semibold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition"
            >
              Back to Recorder
            </button>

            {!reviewRequired ? (
              <button
                onClick={handleStartCompile}
                disabled={isCompiling}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition disabled:opacity-50"
              >
                <Sparkles className={`w-4 h-4 text-indigo-300 ${isCompiling ? 'animate-spin' : ''}`} />
                {isCompiling ? `Gemma Analyzing... (${compileElapsed}s)` : 'Compile Skill with Gemma 4'}
              </button>
            ) : (
              <button
                onClick={handleApproveAndSave}
                disabled={isCompiling}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 transition disabled:opacity-50"
              >
                <Check className={`w-4 h-4 ${isCompiling ? 'animate-spin' : ''}`} />
                {isCompiling ? `Verifying... (${compileElapsed}s)` : 'Approve & Execute Trial'}
              </button>
            )}
          </div>
        </div>

        {compileStatus && (
          <div className="mt-4 p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/30 text-indigo-300 text-xs flex items-center gap-2">
            <Sparkles className={`w-4 h-4 text-indigo-400 shrink-0 ${isCompiling ? 'animate-spin' : ''}`} />
            <span>{compileStatus} {isCompiling ? `(${compileElapsed}s)` : ''}</span>
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-950/50 border border-red-800 text-red-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      
      <div className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">
            Step Semantic Intents &amp; Parameters
          </h3>
          <span className="text-xs text-slate-500">
            Review deduced actions and toggle dynamic variables
          </span>
        </div>

        {steps.map((step) => {
          const isVar = step.role === 'variable' || (step.value && step.value.startsWith('{{') && step.value.endsWith('}}'));
          return (
            <div
              key={step.idx}
              className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition space-y-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="w-8 h-8 rounded-xl bg-indigo-950 text-indigo-300 border border-indigo-800/40 font-mono text-xs font-bold flex items-center justify-center shrink-0">
                    #{step.idx}
                  </span>
                  <div>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold uppercase tracking-wider bg-slate-800 text-slate-300">
                      {step.action}
                    </span>
                    {step.locators?.[0] && (
                      <span className="ml-2 text-xs font-mono text-slate-400">
                        {step.locators[0].kind}: {step.locators[0].value || step.locators[0].name}
                      </span>
                    )}
                  </div>
                </div>

                
                {step.action !== 'goto' && (
                  <button
                    onClick={() => handleToggleVariable(step.idx)}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition ${
                      isVar
                        ? 'bg-purple-950/70 border border-purple-500/40 text-purple-300'
                        : 'bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Tag className="w-3.5 h-3.5" />
                    {isVar ? 'Dynamic Input Variable' : 'Constant Static Step'}
                  </button>
                )}
              </div>

              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label htmlFor={`intent-input-${step.idx}`} className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Sparkles className="w-3 h-3 text-indigo-400" />
                    Semantic Intent (Inferred by Gemma 4)
                  </label>
                  <input
                    type="text"
                    value={step.intent || ''}
                    placeholder="e.g. Choose applicant's department"
                    id={`intent-input-${step.idx}`}
                    aria-label={`Semantic Intent for Step ${step.idx}`}
                    onChange={(e) => handleStepIntentChange(step.idx, e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <div className="space-y-1">
                  <span className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    {isVar ? 'Parameter Variable Name' : 'Literal Step Value'}
                  </span>
                  {isVar ? (
                    <div className="flex items-center gap-1">
                      <span className="text-xs font-mono text-purple-400 font-bold">{'{'}{'{'}</span>
                      <input
                        type="text"
                        value={step.variable_name || ''}
                        placeholder="applicant_name"
                        id={`var-input-${step.idx}`}
                        aria-label={`Parameter Variable Name for Step ${step.idx}`}
                        onChange={(e) => handleVariableNameChange(step.idx, e.target.value)}
                        className="flex-1 bg-slate-950 border border-purple-800/40 rounded-lg px-2.5 py-1.5 text-xs text-purple-300 font-mono focus:outline-none focus:ring-1 focus:ring-purple-500"
                      />
                      <span className="text-xs font-mono text-purple-400 font-bold">{'}'}{'}'}</span>
                    </div>
                  ) : (
                    <input
                      type="text"
                      value={step.value || ''}
                      id={`static-val-${step.idx}`}
                      aria-label={`Static Constant Value for Step ${step.idx}`}
                      placeholder="Static constant value"
                      disabled={step.action === 'click'}
                      onChange={(e) => {
                        const val = e.target.value;
                        setSteps(prev => prev.map(s => s.idx === step.idx ? { ...s, value: val } : s));
                      }}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-40"
                    />
                  )}
                </div>
              </div>

              
              <div className="pt-2 flex items-center gap-3">
                {step.shot_before && (
                  <button
                    onClick={() => setSelectedShot(step.shot_before!)}
                    className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-indigo-400 transition"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    View Pre-Action Snapshot
                  </button>
                )}
                {step.shot_after && (
                  <button
                    onClick={() => setSelectedShot(step.shot_after!)}
                    className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-indigo-400 transition"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    View Post-Action Snapshot
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      
      {selectedShot && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={() => setSelectedShot(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-4 max-w-4xl w-full max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-semibold text-slate-300">Interaction Visual Snapshot</span>
              <button
                onClick={() => setSelectedShot(null)}
                className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded bg-slate-800"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto pt-4 flex items-center justify-center">
              <img
                src={getImageUrl(selectedShot)}
                alt="Snapshot Full View"
                className="max-w-full max-h-[75vh] rounded-lg border border-slate-800"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
