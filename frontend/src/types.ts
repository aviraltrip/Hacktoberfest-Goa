export type ActionType = 'goto' | 'click' | 'fill' | 'select' | 'check' | 'press';
export type LocatorKind = 'role' | 'label' | 'placeholder' | 'text' | 'testid' | 'css';

export interface Locator {
  kind: LocatorKind;
  value: string;
  name?: string | null;
}

export interface Step {
  idx: number;
  action: ActionType;
  locators: Locator[];
  value?: string | null;
  intent: string;
  role?: 'variable' | 'constant';
  variable_name?: string | null;
  shot_before?: string;
  shot_after?: string;
  dom_context?: string;
}

export interface Variable {
  name: string;
  type: 'text' | 'select' | 'date' | 'number';
  example: string;
  options: string[];
}

export interface SuccessCondition {
  text_visible?: string | null;
  url_contains?: string | null;
  visual: string;
}

export interface WorkflowSpec {
  id: string;
  name: string;
  start_url: string;
  variables: Variable[];
  steps: Step[];
  success: SuccessCondition;
  created_at?: string;
}

export interface StepResult {
  idx: number;
  ok: boolean;
  error?: string | null;
  shot?: string | null;
}

export interface RowResult {
  row_idx: number;
  row_data: Record<string, any>;
  steps: StepResult[];
  success: boolean;
  evidence?: string | null;
}

export interface CandidateElement {
  id: number;
  tag: string;
  role?: string;
  aria_label?: string;
  text?: string;
  title?: string;
  placeholder?: string;
  id_attr?: string;
  classes?: string[];
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  bm25_score?: number;
}

export interface HealProposal {
  step_idx: number;
  choice: number;
  explanation: string;
  som_shot: string;
  original_shot: string;
  candidate?: CandidateElement | null;
  proposed_locator?: Locator | null;
}

export interface GemmaCallLog {
  id: string;
  timestamp: string;
  endpoint: 'understand_step' | 'understand_workflow' | 'heal_choice' | 'verify_visual';
  model: string;
  prompt_summary: string;
  image_paths: string[];
  response_raw: string;
  parsed_json?: Record<string, any> | null;
  latency_ms: number;
  status: 'success' | 'retry' | 'error';
  error?: string | null;
}

export interface AblationBenchmark {
  id: string;
  name: string;
  description: string;
  bm25_score: number;
  gemma_score: number;
  reason: string;
}

export interface AblationResponse {
  benchmark_results: AblationBenchmark[];
  summary: {
    bm25_average: number;
    gemma_average: number;
    delta_improvement: number;
  };
}
