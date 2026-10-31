import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, 
  Plus, 
  Trash2, 
  CheckCircle2, 
  XCircle, 
  Loader2, 
  AlertTriangle, 
  ShieldCheck, 
  FileSpreadsheet, 
  Eye, 
  RotateCcw,
  Monitor,
  Wrench,
  Check
} from 'lucide-react';
import { WorkflowSpec, RowResult, HealProposal } from '../types';
import { startWorkflowRun, listSpecs, listRuns, getImageUrl } from '../api';

interface RunGridProps {
  currentSpec?: WorkflowSpec | null;
  onHealTriggered: (runId: string, proposal: HealProposal) => void;
}

const DEFAULT_ROWS = [
  { fullName: 'Aarav Patel', department: 'Computer Science', gradYear: '2026', sop: 'Interested in AI research.' },
  { fullName: 'Maya Sharma', department: 'Information Technology', gradYear: '2027', sop: 'Focus on distributed cloud systems.' },
  { fullName: 'Rohan Rao', department: 'Electronics', gradYear: '2028', sop: 'Embedded robotics and IoT applications.' }
];

export default function RunGrid({ currentSpec, onHealTriggered }: RunGridProps) {
  const [specs, setSpecs] = useState<WorkflowSpec[]>([]);
  const [selectedSpecId, setSelectedSpecId] = useState<string>(currentSpec?.id || '');
  const [rows, setRows] = useState<Record<string, any>[]>(DEFAULT_ROWS);
  const [headed, setHeaded] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [results, setResults] = useState<RowResult[]>([]);
  const [currentStepIdx, setCurrentStepIdx] = useState<{ rowIdx: number; stepIdx: number } | null>(null);
  const [previewShot, setPreviewShot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    loadSpecs();
  }, []);

  useEffect(() => {
    if (currentSpec) {
      setSelectedSpecId(currentSpec.id);
    }
  }, [currentSpec]);

  const loadSpecs = async () => {
    try {
      const data = await listSpecs();
      setSpecs(data);
      if (data.length > 0 && !selectedSpecId) {
        setSelectedSpecId(data[0].id);
      }
    } catch (e) {
      console.error('Failed to load specs', e);
    }
  };

  const activeSpec = specs.find(s => s.id === selectedSpecId) || currentSpec;

  const handleAddRow = () => {
    const newRow: Record<string, any> = {};
    if (activeSpec?.variables) {
      activeSpec.variables.forEach(v => {
        newRow[v.name] = v.example || '';
      });
    } else {
      newRow['fullName'] = 'New Applicant';
      newRow['department'] = 'Computer Science';
    }
    setRows(prev => [...prev, newRow]);
  };

  const handleRemoveRow = (index: number) => {
    setRows(prev => prev.filter((_, i) => i !== index));
  };

  const handleCellChange = (rowIndex: number, field: string, value: string) => {
    setRows(prev => prev.map((r, i) => i === rowIndex ? { ...r, [field]: value } : r));
  };

  const handleStartBatch = async () => {
    if (!selectedSpecId && !activeSpec?.id) {
      setError('Please select or compile a workflow skill first.');
      return;
    }
    const specId = selectedSpecId || activeSpec!.id;
    setIsRunning(true);
    setError(null);
    setResults([]);
    setCurrentStepIdx(null);

    try {
      const res = await startWorkflowRun(specId, rows, headed);
      setActiveRunId(res.run_id);

      const es = new EventSource(`/api/run/${res.run_id}/events`);
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'step_start') {
            setCurrentStepIdx({ rowIdx: data.row_idx, stepIdx: data.step_idx });
          } else if (data.type === 'row_completed') {
            setResults(prev => {
              const existing = prev.filter(r => r.row_idx !== data.row_idx);
              return [...existing, data.result].sort((a, b) => a.row_idx - b.row_idx);
            });
          } else if (data.type === 'heal_required' || data.type === 'heal_proposal') {
            // Trigger Set-of-Marks heal review modal
            if (data.proposal) {
              onHealTriggered(res.run_id, data.proposal);
            }
          } else if (data.type === 'heal_approved') {
            // Resumed after heal approval
            console.log('Heal approved and spec patched. Resuming rows...');
          } else if (data.type === 'run_completed' || data.status === 'completed') {
            setIsRunning(false);
            setCurrentStepIdx(null);
            es.close();
          }
        } catch (e) {
          console.error('Error parsing run SSE event:', e);
        }
      };

      es.onerror = () => {
        es.close();
      };

      eventSourceRef.current = es;
    } catch (err: any) {
      setError(err.message || 'Failed to start workflow execution');
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Run Configuration Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2 flex-1">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Active Workflow Skill
            </label>
            <div className="flex items-center gap-3">
              <select
                value={selectedSpecId}
                disabled={isRunning}
                onChange={(e) => setSelectedSpecId(e.target.value)}
                className="bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium max-w-md w-full"
              >
                {specs.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.steps.length} steps, {s.variables.length} vars)
                  </option>
                ))}
                {currentSpec && !specs.some(s => s.id === currentSpec.id) && (
                  <option value={currentSpec.id}>
                    {currentSpec.name} (Active in Memory)
                  </option>
                )}
              </select>

              {activeSpec && (
                <span className="text-xs text-slate-400 font-mono hidden sm:inline">
                  URL: {activeSpec.start_url}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2 lg:pt-6">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={headed}
                disabled={isRunning}
                onChange={(e) => setHeaded(e.target.checked)}
                className="w-4 h-4 rounded text-indigo-600 bg-slate-950 border-slate-700 focus:ring-indigo-500"
              />
              <span className="flex items-center gap-1.5">
                <Monitor className="w-3.5 h-3.5 text-slate-400" />
                Headed Chromium Replay
              </span>
            </label>

            <button
              onClick={handleStartBatch}
              disabled={isRunning || rows.length === 0}
              className="flex items-center gap-2 px-6 py-2.5 rounded-xl font-semibold text-sm bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition disabled:opacity-50"
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                  Executing Batch...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  Run Batch ({rows.length} rows)
                </>
              )}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-950/50 border border-red-800 text-red-300 text-xs">
            {error}
          </div>
        )}
      </div>

      {/* Input Data Rows Editor */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Batch Inputs Parameter Matrix
            </h3>
          </div>
          <button
            onClick={handleAddRow}
            disabled={isRunning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Row
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2.5 px-3 font-semibold w-12">#</th>
                <th className="py-2.5 px-3 font-semibold">Full Name</th>
                <th className="py-2.5 px-3 font-semibold">Department</th>
                <th className="py-2.5 px-3 font-semibold">Graduation Year</th>
                <th className="py-2.5 px-3 font-semibold">Statement of Purpose</th>
                <th className="py-2.5 px-3 font-semibold w-12 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {rows.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-slate-800/20 transition">
                  <td className="py-2 px-3 font-mono text-slate-500 font-bold">{rIdx + 1}</td>
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={row.fullName || ''}
                      disabled={isRunning}
                      onChange={(e) => handleCellChange(rIdx, 'fullName', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </td>
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={row.department || ''}
                      disabled={isRunning}
                      onChange={(e) => handleCellChange(rIdx, 'department', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </td>
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={row.gradYear || ''}
                      disabled={isRunning}
                      onChange={(e) => handleCellChange(rIdx, 'gradYear', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </td>
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={row.sop || ''}
                      disabled={isRunning}
                      onChange={(e) => handleCellChange(rIdx, 'sop', e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </td>
                  <td className="py-2 px-3 text-center">
                    <button
                      onClick={() => handleRemoveRow(rIdx)}
                      disabled={isRunning || rows.length <= 1}
                      className="text-slate-500 hover:text-red-400 p-1 transition disabled:opacity-30"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Execution Results Matrix */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-300">
              Live Execution Matrix &amp; Verification Evidence
            </h3>
          </div>
          {results.length > 0 && (
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              {results.filter(r => r.success).length} / {rows.length} Rows Verified
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-3 px-3 font-semibold w-16">Row #</th>
                <th className="py-3 px-3 font-semibold">Applicant Input</th>
                {activeSpec?.steps.map(s => (
                  <th key={s.idx} className="py-3 px-2 font-semibold text-center font-mono">
                    Step {s.idx}
                  </th>
                ))}
                <th className="py-3 px-3 font-semibold text-center">Outcome</th>
                <th className="py-3 px-3 font-semibold text-right">Visual Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {rows.map((row, rIdx) => {
                const rowResult = results.find(r => r.row_idx === rIdx + 1);
                const isCurrentRow = currentStepIdx?.rowIdx === rIdx + 1;

                return (
                  <tr key={rIdx} className="hover:bg-slate-800/20 transition">
                    <td className="py-3 px-3 font-mono font-bold text-slate-400">
                      Row {rIdx + 1}
                    </td>
                    <td className="py-3 px-3">
                      <div className="font-semibold text-slate-200">
                        {row.fullName || `Row #${rIdx + 1}`}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        {row.department} {row.gradYear ? `(${row.gradYear})` : ''}
                      </div>
                    </td>

                    {/* Step Status Badges */}
                    {activeSpec?.steps.map(step => {
                      const stepRes = rowResult?.steps?.find(s => s.idx === step.idx);
                      const isCurrentStep = isCurrentRow && currentStepIdx?.stepIdx === step.idx;

                      return (
                        <td key={step.idx} className="py-3 px-2 text-center">
                          {isCurrentStep ? (
                            <div className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 animate-pulse">
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            </div>
                          ) : stepRes ? (
                            stepRes.ok ? (
                              <div className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                <CheckCircle2 className="w-4 h-4" />
                              </div>
                            ) : (
                              <div
                                title={stepRes.error || 'Step Failed'}
                                className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-500/10 text-red-400 border border-red-500/20 cursor-help"
                              >
                                <XCircle className="w-4 h-4" />
                              </div>
                            )
                          ) : (
                            <div className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-slate-800/40 text-slate-600">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-700" />
                            </div>
                          )}
                        </td>
                      );
                    })}

                    {/* Outcome Badge */}
                    <td className="py-3 px-3 text-center">
                      {rowResult ? (
                        rowResult.success ? (
                          <span className="px-2.5 py-1 rounded-full font-semibold text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            Verified Pass
                          </span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-full font-semibold text-[11px] bg-red-500/10 text-red-400 border border-red-500/20">
                            Failed
                          </span>
                        )
                      ) : isCurrentRow ? (
                        <span className="px-2.5 py-1 rounded-full font-semibold text-[11px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse">
                          Running...
                        </span>
                      ) : (
                        <span className="text-slate-600 text-[11px]">Queued</span>
                      )}
                    </td>

                    {/* Visual Evidence Snapshot */}
                    <td className="py-3 px-3 text-right">
                      {rowResult?.evidence ? (
                        <button
                          onClick={() => setPreviewShot(rowResult.evidence!)}
                          className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-medium transition"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          View Proof
                        </button>
                      ) : (
                        <span className="text-slate-600 text-[11px]">Pending</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Snapshot Preview Modal */}
      {previewShot && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={() => setPreviewShot(null)}>
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5 max-w-4xl w-full max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Final State Verification Proof
              </span>
              <button
                onClick={() => setPreviewShot(null)}
                className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded bg-slate-800"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto pt-4 flex items-center justify-center">
              <img
                src={getImageUrl(previewShot)}
                alt="Verification Proof"
                className="max-w-full max-h-[75vh] rounded-lg border border-slate-800"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
