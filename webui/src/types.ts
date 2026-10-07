export type CardType = 'plot' | 'character' | 'scene' | 'faction' | 'item' | 'rule';
export type WorkspaceView = 'pipeline' | 'assets' | 'ecosystem' | CardType | 'chapters' | 'context';

export interface ApiEnvelope<T> {
  status: 'ok' | 'error';
  message: string;
  data: T;
}

export interface ProjectSummary {
  project_id: string;
  path: string;
}

export interface ProjectMeta {
  project_id: string;
  run_count: number;
  chapter_count: number;
}

export interface StatusCard {
  card_id: string;
  card_type: CardType;
  card_name: string;
  subject_id?: string | null;
  summary?: string | null;
  current_state?: unknown;
  constraints?: string[];
  reader_needs?: string[];
  reader_knowledge?: string[];
  character_knowledge?: Record<string, unknown>;
  open_questions?: string[];
  source_refs?: Array<Record<string, unknown>>;
  source_version?: number;
  last_touched_event_id?: string | null;
  revelation_gate?: Record<string, unknown> | null;
  attributes?: Record<string, unknown>;
}

export interface ContextSource {
  source_id: string;
  authority: string;
  version?: number | null;
  path: string;
  reason: string;
  protected: boolean;
  estimated_tokens: number;
}

export interface ContextCard {
  card_id: string;
  card_name: string;
  card_type: CardType;
  reason: string;
  priority: 'high' | 'medium' | 'low';
  relevance_score: number;
  estimated_tokens: number;
}

export interface ContextTrace {
  context_id: string;
  fingerprint: string;
  focus: string;
  sources: ContextSource[];
  cards: ContextCard[];
  omitted: Array<{ source_id: string; reason: string }>;
  source_versions: Record<string, number>;
  estimated_tokens: number;
  token_budget: number;
  compiled_context?: Record<string, unknown>;
}

export interface Snapshot {
  snapshot_key?: string;
  event_id?: string;
  location?: string | null;
  time_in_story?: string | null;
  result_state_summary?: string | null;
  resources?: Record<string, unknown>;
  hp?: Record<string, unknown>;
  ability_boundary?: string[];
  relationship_state?: Record<string, unknown>;
  entity_states?: Record<string, Record<string, unknown>>;
  narrative_line_states?: Record<string, Record<string, unknown>>;
  entity_agendas?: Record<string, Record<string, unknown>>;
  asset_states?: Record<string, Record<string, unknown>>;
  timeline_events?: Array<Record<string, unknown>>;
  open_threads?: string[];
  reading_focus?: Array<Record<string, unknown>>;
  context_fingerprint?: string | null;
}

export interface StateData {
  char: Record<string, unknown>;
  char_version: number;
  latest_state: Snapshot | null;
  status_cards: Partial<Record<`${CardType}_cards`, StatusCard[]>>;
  card_index_version: number;
  latest_context: ContextTrace | null;
}

export interface ChapterSummary {
  chapter_id: string;
  chapter_index: number;
  title?: string;
  chapter_intent?: string;
  word_count?: number;
  committed_at?: string;
  created_at?: string;
}

export interface ActivityEntry {
  id: string;
  at: string;
  event: string;
  message: string;
  data?: Record<string, unknown>;
  level: 'info' | 'success' | 'warning' | 'error';
}

export interface RunResult {
  run_id?: string;
  event_id?: string;
  word_count?: number;
  chapters_generated?: number;
  diff_passed?: boolean;
  fix_attempts?: number;
  quality_attempts?: number;
  quality_report?: {
    score?: number;
    passed?: boolean;
    issues?: string[];
    threshold?: number;
    selected_attempt?: number;
    attempts?: Array<Record<string, unknown>>;
    metrics?: Record<string, number>;
  };
  context_fingerprint?: string;
  compiled_context?: Record<string, unknown>;
  execution_report?: {
    event_route?: Record<string, unknown>;
    world_pulse?: Record<string, unknown>;
    event_expansion?: Record<string, unknown>;
    prewrite_check?: Record<string, unknown>;
    scene_plan?: Array<Record<string, unknown>>;
    jit_cards?: Array<Record<string, unknown>>;
  };
  context_summary?: {
    focus?: string;
    estimated_tokens?: number;
    token_budget?: number;
    sources?: Array<Record<string, unknown>>;
    cards?: Array<Record<string, unknown>>;
  };
  state_writeback?: {
    summary?: string;
    changed_items?: string[];
    new_entities?: string[];
    retired_entities?: string[];
    narrative_line_updates?: Array<Record<string, unknown>>;
    entity_agenda_updates?: Array<Record<string, unknown>>;
    asset_lifecycle_updates?: Array<Record<string, unknown>>;
    timeline_updates?: Array<Record<string, unknown>>;
    plan_adjustment_requests?: Array<Record<string, unknown>>;
  };
  chapters?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface WorkflowStage {
  id: 'foundation' | 'master_plan' | 'volume_plan' | 'event_plan' | 'prose' | 'state_delta' | 'chapter_plan';
  label: string;
  status: 'locked' | 'available' | 'pending' | 'approved';
}

export type WorkflowReviewKind = WorkflowStage['id'] | 'asset_edit';

export interface ReviewAuditResult {
  verdict: 'pass' | 'revise' | string;
  summary: string;
  strengths: string[];
  issues: Array<{
    severity: string;
    category: string;
    location_anchor: string;
    problem: string;
    authority_basis: string;
    revision_instruction: string;
  }>;
  revision_feedback: string;
}

export interface WorkflowReview {
  staging_id: string;
  run_id: string;
  review_kind: WorkflowReviewKind;
  title: string;
  status: 'pending' | 'approved' | 'rejected';
  editable: Record<string, unknown>;
  asset_meta?: AssetSummary | null;
  original_content?: unknown;
  foundation_step?: string | null;
  master_step?: string | null;
  volume_step?: string | null;
  event_plan_step?: string | null;
  event_id?: string | null;
  event_index?: number | null;
  volume_index?: number | null;
  asset_id?: string | null;
  max_tokens?: number | null;
  step_index?: number | null;
  step_total?: number | null;
  budget_report?: Record<string, unknown> | null;
  quality_report?: RunResult['quality_report'] | null;
  prewrite_check?: Record<string, unknown> | null;
  revision_count?: number;
  revision_history?: Array<{
    revision_no: number;
    feedback: string;
    change_summary: string;
    preserved_summary?: string;
    before_editable?: Record<string, unknown>;
    created_at: string;
    input_tokens?: number;
    output_tokens?: number;
  }>;
  audit_count?: number;
  audit_history?: Array<{
    audit_no: number;
    report: ReviewAuditResult;
    audited_editable?: Record<string, unknown>;
    basis_revision_count?: number;
    created_at: string;
    input_tokens?: number;
    output_tokens?: number;
  }>;
  current_audit?: ReviewAuditResult | null;
  suggested_feedback?: string;
  created_at: string;
}

export interface FoundationStepProgress {
  id: string;
  label: string;
  index: number;
  status: 'locked' | 'available' | 'pending' | 'approved';
}

export interface FoundationProgress {
  approved_count: number;
  total: number;
  complete: boolean;
  next_step: string | null;
  brief: string;
  invalidated?: Record<string, { reason?: string; from_step?: string; invalidated_at?: string }>;
  steps: FoundationStepProgress[];
}

export interface MasterPlanStepProgress extends FoundationStepProgress {
  asset_id: string;
  max_tokens: number;
  character_id?: string | null;
}

export interface MasterPlanProgress {
  approved_count: number;
  total: number;
  complete: boolean;
  next_step: string | null;
  complexity_level: 'low' | 'medium' | 'high' | string;
  total_output_budget: number;
  steps: MasterPlanStepProgress[];
}

export interface VolumePlanStepProgress extends FoundationStepProgress {
  asset_id: string;
  max_tokens: number;
  start_event?: number | null;
  end_event?: number | null;
}

export interface VolumePlanProgress {
  approved_count: number;
  total: number;
  complete: boolean;
  next_step: string | null;
  volume_index: number;
  events_per_volume: number;
  total_output_budget: number;
  steps: VolumePlanStepProgress[];
}

export interface EventPlanStepProgress extends FoundationStepProgress {
  asset_id: string;
  max_tokens: number;
}

export interface EventPlanProgress {
  event_id: string;
  event_index: number;
  approved_count: number;
  total: number;
  complete: boolean;
  next_step: string | null;
  total_output_budget: number;
  steps: EventPlanStepProgress[];
}

export interface WorkflowData {
  stages: WorkflowStage[];
  reviews: WorkflowReview[];
  pending_reviews: WorkflowReview[];
  event_slots: Array<Record<string, unknown>>;
  completed_events: number;
  next_event_index: number;
  foundation_progress: FoundationProgress;
  master_plan_progress: MasterPlanProgress;
  volume_plan_progress: VolumePlanProgress;
  event_plan_progress: Record<string, EventPlanProgress>;
}

export type AssetScope = 'foundation' | 'master' | 'volume' | 'event' | 'runtime';
export type AssetEditorKind = 'object' | 'collection' | 'text' | 'readonly';

export interface AssetSummary {
  asset_id: string;
  group_id: string;
  group_label: string;
  label: string;
  scope: AssetScope;
  artifact_key: string | null;
  json_path: string;
  excluded_keys: string[];
  editor_kind: AssetEditorKind;
  description: string;
  editable: boolean;
  derived: boolean;
  exists: boolean;
  version: number;
  item_count: number;
  owner_stage: string;
  dependencies: string[];
  downstream: string[];
  source_asset_id: string | null;
}

export interface AssetDetail extends AssetSummary {
  content: unknown;
}

export interface AssetGroup {
  group_id: string;
  label: string;
  scope: AssetScope;
  asset_ids: string[];
}

export interface AssetCatalog {
  groups: AssetGroup[];
  assets: AssetSummary[];
}
