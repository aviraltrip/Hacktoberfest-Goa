import { WorkflowSpec, Variable, Step, GemmaCallLog, AblationResponse } from './types';

const API_BASE = '/api';

export function getImageUrl(path?: string | null): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('/static/')) {
    return path;
  }
  // If filename or relative path
  const filename = path.replace(/\\/g, '/').split('/').pop();
  return `/static/shots/${filename}`;
}

export async function startRecording(startUrl: string, headed: boolean = true) {
  const res = await fetch(`${API_BASE}/record/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_url: startUrl, headed }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ recording_id: string; status: string }>;
}

export async function stopRecording(recordingId: string) {
  const res = await fetch(`${API_BASE}/record/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recording_id: recordingId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ recording_id: string; step_count: number; raw_steps: Step[] }>;
}

export async function startCompilation(recordingId: string) {
  const res = await fetch(`${API_BASE}/compile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recording_id: recordingId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ compile_id: string; status: string }>;
}

export async function approveCompilation(compileId: string, updates: { name?: string; variables?: Variable[]; steps?: Step[] }) {
  const res = await fetch(`${API_BASE}/compile/${compileId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ compile_id: string; status: string }>;
}

export async function startWorkflowRun(specId: string, rows: Record<string, any>[], headed: boolean = false) {
  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spec_id: specId, rows, headed }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ run_id: string; status: string }>;
}

export async function approveHealAction(runId: string, approved: boolean, overrideChoice?: number) {
  const res = await fetch(`${API_BASE}/run/${runId}/approve_heal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, override_choice: overrideChoice }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<{ run_id: string; status: string }>;
}

export async function listSpecs(): Promise<WorkflowSpec[]> {
  const res = await fetch(`${API_BASE}/specs`);
  if (!res.ok) return [];
  return res.json();
}

export async function getSpec(id: string): Promise<WorkflowSpec> {
  const res = await fetch(`${API_BASE}/specs/${id}`);
  if (!res.ok) throw new Error('Spec not found');
  return res.json();
}

export async function exportStandaloneScript(id: string): Promise<{ spec: WorkflowSpec; playwright_script: string }> {
  const res = await fetch(`${API_BASE}/specs/${id}/export`);
  if (!res.ok) throw new Error('Export failed');
  return res.json();
}

export async function listRuns(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/runs`);
  if (!res.ok) return [];
  return res.json();
}

export async function getGemmaCalls(): Promise<GemmaCallLog[]> {
  const res = await fetch(`${API_BASE}/gemma/calls`);
  if (!res.ok) return [];
  return res.json();
}

export async function getHealMemory(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/heal/memory`);
  if (!res.ok) return [];
  return res.json();
}

export async function getAblationBenchmark(): Promise<AblationResponse> {
  const res = await fetch(`${API_BASE}/ablation`);
  if (!res.ok) throw new Error('Ablation benchmark fetch failed');
  return res.json();
}
