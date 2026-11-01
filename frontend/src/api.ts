import { WorkflowSpec, Variable, Step, GemmaCallLog, AblationResponse } from './types';

const API_BASE = '/api';

export function getImageUrl(path?: string | null): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('/static/')) {
    return path;
  }
  
  const filename = path.replace(/\\/g, '/').split('/').pop();
  return `/static/shots/${filename}`;
}

async function handleResponse<T>(res: Response, defaultError = 'Request failed'): Promise<T> {
  if (!res.ok) {
    let msg = defaultError;
    try {
      const rawText = await res.text();
      msg = rawText || defaultError;
      const errJson = JSON.parse(rawText);
      if (errJson && errJson.detail) {
        msg = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export async function startRecording(startUrl: string, headed: boolean = true) {
  const res = await fetch(`${API_BASE}/record/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_url: startUrl, headed }),
  });
  return handleResponse<{ recording_id: string; status: string }>(res, 'Failed to start recording');
}

export async function stopRecording(recordingId: string) {
  const res = await fetch(`${API_BASE}/record/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recording_id: recordingId }),
  });
  return handleResponse<{ recording_id: string; step_count: number; steps?: Step[]; raw_steps?: Step[] }>(
    res,
    'Failed to stop recording'
  );
}

export async function startCompilation(recordingId: string) {
  const res = await fetch(`${API_BASE}/compile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recording_id: recordingId }),
  });
  return handleResponse<{ compile_id: string; status: string }>(res, 'Failed to start compilation');
}

export async function getCompilation(compileId: string) {
  const res = await fetch(`${API_BASE}/compile/${compileId}`);
  return handleResponse<{ compile_id: string; status: string; payload: any; spec?: any; error?: string }>(
    res,
    'Failed to fetch compilation status'
  );
}

export async function approveCompilation(compileId: string, updates: { name?: string; variables?: Variable[]; steps?: Step[] }) {
  const res = await fetch(`${API_BASE}/compile/${compileId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  return handleResponse<{ compile_id: string; status: string }>(res, 'Failed to approve compilation');
}

export async function startWorkflowRun(specId: string, rows: Record<string, any>[], headed: boolean = false) {
  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spec_id: specId, rows, headed }),
  });
  return handleResponse<{ run_id: string; status: string }>(res, 'Failed to start workflow run');
}

export async function approveHealAction(runId: string, approved: boolean, overrideChoice?: number) {
  const res = await fetch(`${API_BASE}/run/${runId}/approve_heal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, override_choice: overrideChoice }),
  });
  return handleResponse<{ run_id: string; status: string }>(res, 'Failed to submit heal approval');
}

export async function listSpecs(): Promise<WorkflowSpec[]> {
  const res = await fetch(`${API_BASE}/specs`);
  if (!res.ok) return [];
  return res.json();
}

export async function getSpec(id: string): Promise<WorkflowSpec> {
  const res = await fetch(`${API_BASE}/specs/${id}`);
  return handleResponse<WorkflowSpec>(res, 'Spec not found');
}

export async function exportStandaloneScript(id: string): Promise<{ spec: WorkflowSpec; playwright_script: string }> {
  const res = await fetch(`${API_BASE}/specs/${id}/export`);
  return handleResponse<{ spec: WorkflowSpec; playwright_script: string }>(res, 'Export failed');
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
  return handleResponse<AblationResponse>(res, 'Ablation benchmark fetch failed');
}
