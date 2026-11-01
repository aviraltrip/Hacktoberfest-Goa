import React, { useState } from 'react';
import { 
  Wrench, 
  Sparkles, 
  Check, 
  X, 
  AlertTriangle, 
  Layers, 
  CheckCircle2, 
  Eye, 
  ArrowRight,
  ShieldAlert,
  HelpCircle
} from 'lucide-react';
import { HealProposal, CandidateElement } from '../types';
import { approveHealAction, getImageUrl } from '../api';

interface HealModalProps {
  runId: string;
  proposal: HealProposal;
  onClose: () => void;
  onHealResolved: (approved: boolean) => void;
}

export default function HealModal({
  runId,
  proposal,
  onClose,
  onHealResolved
}: HealModalProps) {
  const [selectedChoice, setSelectedChoice] = useState<number>(proposal.choice || 1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApprove = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      await approveHealAction(runId, true, selectedChoice);
      onHealResolved(true);
    } catch (err: any) {
      setError(err.message || 'Failed to approve healing proposal');
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      await approveHealAction(runId, false);
      onHealResolved(false);
    } catch (err: any) {
      setError(err.message || 'Failed to reject healing proposal');
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      <div 
        className="bg-slate-900 border border-slate-700 rounded-3xl max-w-5xl w-full max-h-[92vh] flex flex-col shadow-2xl overflow-hidden my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        
        <div className="px-6 py-4 bg-gradient-to-r from-amber-950/60 via-slate-900 to-indigo-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-amber-500/20 border border-amber-500/30 text-amber-400">
              <Wrench className="w-5 h-5 animate-spin" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-base text-white tracking-tight">
                  Self-Healing Required: Step #{proposal.step_idx}
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-indigo-400" />
                  Gemma 4 Set-of-Marks
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Target element selector broke on UI mutation. Gemma 4 visually identified the replacement.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-xl bg-slate-800 hover:bg-slate-700 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider">
                <span>Original Recorded State</span>
                <span className="text-[11px] text-slate-500 font-normal">Pre-mutation baseline</span>
              </div>
              <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden aspect-video flex items-center justify-center p-2 relative group">
                {proposal.original_shot ? (
                  <img
                    src={getImageUrl(proposal.original_shot)}
                    alt="Original State"
                    className="max-h-full max-w-full object-contain rounded-lg"
                  />
                ) : (
                  <span className="text-xs text-slate-600">No original snapshot</span>
                )}
                <span className="absolute top-3 left-3 px-2 py-0.5 rounded bg-black/70 text-[10px] text-slate-300 font-mono">
                  Original
                </span>
              </div>
            </div>

            
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-indigo-300 uppercase tracking-wider">
                <span className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Mutated Page with Set-of-Marks
                </span>
                <span className="text-[11px] text-indigo-400 font-normal">Live candidate boxes</span>
              </div>
              <div className="bg-slate-950 border-2 border-indigo-500/40 rounded-2xl overflow-hidden aspect-video flex items-center justify-center p-2 relative group shadow-lg shadow-indigo-950/50">
                {proposal.som_shot ? (
                  <img
                    src={getImageUrl(proposal.som_shot)}
                    alt="Set of Marks Live Overlay"
                    className="max-h-full max-w-full object-contain rounded-lg"
                  />
                ) : (
                  <span className="text-xs text-slate-600">No SoM snapshot</span>
                )}
                <span className="absolute top-3 left-3 px-2 py-0.5 rounded bg-indigo-600/90 text-[10px] text-white font-mono font-bold">
                  Set-of-Marks Overlay
                </span>
              </div>
            </div>
          </div>

          
          <div className="p-5 rounded-2xl bg-indigo-950/40 border border-indigo-500/30 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-indigo-300 font-bold text-sm">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                Gemma 4 Multimodal Deduction
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Selected Box #{proposal.choice}
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed bg-slate-900/60 p-3.5 rounded-xl border border-indigo-800/20">
              &quot;{proposal.explanation}&quot;
            </p>

            {proposal.proposed_locator && (
              <div className="flex items-center gap-2 pt-1 text-xs">
                <span className="text-slate-400 font-medium">Proposed Replacement Locator:</span>
                <code className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-indigo-300 font-mono text-xs font-semibold">
                  {proposal.proposed_locator.kind}: {proposal.proposed_locator.value || proposal.proposed_locator.name}
                </code>
              </div>
            )}
          </div>

          
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Confirm or Override Candidate Choice
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[1, 2, 3, 4, 5, 6, 7, 8].map((num) => (
                <button
                  key={num}
                  type="button"
                  onClick={() => setSelectedChoice(num)}
                  className={`p-3 rounded-xl border text-xs font-mono font-bold flex items-center justify-between transition ${
                    selectedChoice === num
                      ? 'bg-indigo-600 text-white border-indigo-400 shadow-md shadow-indigo-600/30'
                      : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700'
                  }`}
                >
                  <span>Candidate #{num}</span>
                  {num === proposal.choice && (
                    <span className="text-[10px] uppercase font-sans font-normal px-1.5 py-0.5 rounded bg-indigo-800 text-indigo-200">
                      Gemma Pick
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-950/50 border border-red-800 text-red-300 text-xs">
              {error}
            </div>
          )}
        </div>

        
        <div className="px-6 py-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <button
            onClick={handleReject}
            disabled={isSubmitting}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-red-400 transition"
          >
            Reject & Abort Run
          </button>

          <button
            onClick={handleApprove}
            disabled={isSubmitting}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-600/30 transition disabled:opacity-50"
          >
            <Check className="w-4 h-4" />
            {isSubmitting ? 'Patching Spec & Resuming...' : `Approve Box #${selectedChoice} & Resume`}
          </button>
        </div>
      </div>
    </div>
  );
}
