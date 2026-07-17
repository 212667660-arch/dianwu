export interface HealthStatus {
  status: 'live' | 'ready' | 'not_ready'
  reason?: string
}

export interface SourceItem {
  title: string
  url: string
  snippet: string
}

export interface KnowledgeLocator { type: 'page' | 'slide' | 'sheet_rows' | 'paragraph'; start: number; end: number; sheet_name?: string }
export interface KnowledgeSource { reference_id: string; document_id: number; document_name: string; locator_label: string; locator: KnowledgeLocator; chunk_id: number; retrieval_mode: 'keyword' | 'hybrid' }
export interface CapabilityStatus { available: boolean; mode: string; error_code?: string | null; version?: string | null }
export interface KnowledgeStatus { fts: CapabilityStatus; worker: CapabilityStatus; ocr_pack: CapabilityStatus; semantic_pack: CapabilityStatus }
export interface KnowledgeCollection { id: number; name: string; description: string; color: string; document_count: number; bound_session_count: number; created_at: string; updated_at: string }
export interface KnowledgeCollectionInput { name: string; description: string; color: string }
export interface KnowledgeDocument { id: number; sha256: string; display_name: string; extension: string; mime_type: string; byte_size: number; status: string; page_count: number | null; slide_count: number | null; sheet_count: number | null; text_characters: number; chunk_count: number; parser_version: string | null; safe_error_code: string | null; created_at: string; updated_at: string }
export interface KnowledgeImportJob { id: number; document_id: number; status: string; progress: number; stage: string; retryable: boolean; safe_error_code: string | null; cancel_requested: boolean; current_page: number | null; page_count: number | null; eta_seconds: number | null; failed_pages: number[]; version: number; created_at: string; updated_at: string }
export interface KnowledgeBinding { session_id: string; collection_ids: number[]; privacy_mode: 'allow_model_context' | 'local_search_only' }
export interface KnowledgeImportBatch { jobs: KnowledgeImportJob[] }
export type TextbookAccessMode = 'OFFICIAL_READER' | 'LICENSED_DOWNLOAD' | 'EXTERNAL_CATALOG'
export interface TextbookCatalogItem { source_id: string; publisher: string; title: string; stage: '初中' | '高中'; grade: string; semester: string; subject: '数学'; edition: string; official_url: string; access_mode: TextbookAccessMode; license_note: string; verified_at: string; download_url: string | null }
export interface TextbookCatalog { version: string; items: TextbookCatalogItem[] }
export interface KnowledgeSearchResult { mode: 'keyword' | 'hybrid'; items: Array<{ chunk_id: number; document_id: number; document_name: string; text: string; heading_path: string; locator: KnowledgeLocator; score: number; retrieval_mode: 'keyword' | 'hybrid' }> }

export type ArtifactType = 'course_explanation' | 'mind_map' | 'question_bank' | 'extended_reading' | 'adaptive_practice'

export type SafetyStage = 'REQUEST' | 'CONTEXT' | 'PLAN' | 'ARTIFACT' | 'RENDER'
export type SafetyDecision = 'ALLOW' | 'REDACT' | 'REGENERATE' | 'BLOCK'
export type SafetyRiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type SafetyRiskCategory =
  | 'PROMPT_INJECTION'
  | 'SECRET_OR_CREDENTIAL'
  | 'PERSONAL_DATA'
  | 'MINOR_SAFETY'
  | 'SELF_HARM'
  | 'VIOLENCE_OR_WEAPONS'
  | 'ILLEGAL_WRONGDOING'
  | 'CYBER_ABUSE'
  | 'FRAUD_OR_DECEPTION'
  | 'HATE_OR_HARASSMENT'
  | 'DRUG_OR_DANGEROUS_EXPERIMENT'
  | 'ACADEMIC_INTEGRITY'
  | 'HIGH_STAKES_ADVICE'
  | 'FABRICATED_OR_UNTRUSTED_CITATION'
  | 'ACTIVE_CONTENT_OR_UNSAFE_RENDERING'

export interface SafetyMetadata {
  stage: SafetyStage
  decision: SafetyDecision
  risk_level: SafetyRiskLevel
  categories: SafetyRiskCategory[]
  reason_codes: string[]
  policy_version: 'content-safety/v1'
  reviewer_profile_id: string | null
  checked_at: string
}

export type ResourceSelection =
  | { mode: 'bundle' }
  | { mode: 'single'; resourceType: ArtifactType }

export interface ResourceArtifact {
  artifact_id: string
  type: ArtifactType
  title: string
  status: 'SUCCEEDED' | 'FAILED' | 'CANCELLED'
  body: string
  type_specific_data: Record<string, unknown>
  quality_score: number
  quality_issues: string[]
  error_code: string | null
  retryable: boolean
  safety?: SafetyMetadata | null
}

export interface ResourceBundle {
  bundle_id: string
  protocol_version: 'learning-resource-bundle/v2'
  topic: string
  profile_version: number
  learning_state_version: string
  mode: 'bundle' | 'single'
  status: 'COMPLETED' | 'PARTIAL' | 'FAILED' | 'CANCELLED'
  requested_types: ArtifactType[]
  artifacts: ResourceArtifact[]
  aggregate_quality: number
  created_at: string
  knowledge_sources: KnowledgeSource[]
  public_sources: Array<SourceItem & { reference_id: string }>
}

export interface ChatResponse {
  reply: string
  phase: 'diagnosis' | 'profile' | 'resource'
  state: string
  profile_version: number
  cached: boolean
  sources: SourceItem[]
  knowledge_sources: KnowledgeSource[]
  bundle: ResourceBundle | null
}

export interface SessionMessage {
  seq: number
  role: 'user' | 'assistant'
  content: string
}

export interface QuestionItem {
  id: number
  ordinal: number
  difficulty: '基础' | '提高' | '挑战'
  prompt: string
}

export interface LearningResource {
  id: number
  topic: string
  content: string
  profile_version: number
  learning_state_version: number
  sources: SourceItem[]
  knowledge_sources: KnowledgeSource[]
  quality_score: number
  quality_issues: string[]
  questions: QuestionItem[]
}

export interface SessionHistory {
  session_id: string
  state: string
  profile_version: number
  learning_state_version: number
  profile_text: string | null
  messages: SessionMessage[]
  resources: LearningResource[]
  resource_bundles: ResourceBundle[]
}

export interface KnowledgePoint {
  id: number
  name: string
  subject: string
  mastery_score: number
  mastery_label: 'WEAK' | 'LEARNING' | 'PROFICIENT' | 'MASTERED'
  attempts: number
  correct_attempts: number
  correct_streak: number
  last_error_type: string | null
  last_practiced_at: string | null
  next_review_at: string | null
}

export interface ProgressSnapshot {
  session_id: string
  learning_state_version: number
  total_attempts: number
  correct_attempts: number
  accuracy: number
  knowledge_points: KnowledgePoint[]
}

export interface NextAction {
  session_id: string
  action: 'DIAGNOSE' | 'REVIEW' | 'START_PRACTICE' | 'REMEDIATE' | 'PRACTICE' | 'CONSOLIDATE' | 'CHALLENGE'
  knowledge_point_id: number | null
  knowledge_point: string | null
  recommended_difficulty: string
  reason: string
  due_at: string | null
  suggested_request: string
}

export interface ReviewTask {
  id: number
  knowledge_point_id: number
  knowledge_point: string
  reason: string
  due_at: string
  interval_days: number
  status: string
}

export interface MistakeItem {
  attempt_id: number
  question_id: number
  knowledge_point: string
  prompt: string
  submitted_answer: string
  expected_answer: string
  explanation: string
  error_type: string | null
  created_at: string
}

export interface AttemptResponse {
  attempt_id: number
  question_id: number
  duplicate: boolean
  correct: boolean
  score: number
  submitted_answer: string
  expected_answer: string
  explanation: string
  feedback: string
  error_type: string | null
  mastery_score: number
  mastery_label: string
  next_review_at: string
}

export interface StreamEvent {
  event: string
  request_id?: string
  generation_id?: string
  phase?: string
  content?: string
  state?: string
  status?: string
  code?: string
  message?: string
  sources?: Array<SourceItem | KnowledgeSource>
  knowledge_sources?: KnowledgeSource[]
  resource_id?: number
  profile_version?: number
  learning_state_version?: string
  cached?: boolean
  provisional?: boolean
  profile_id?: string
  model_id?: string
  requested_reasoning_effort?: ReasoningEffort
  effective_reasoning_effort?: ReasoningEffort
  failover_used?: boolean
  can_continue_with_backup?: boolean
  bundle_id?: string
  topic?: string
  requested_types?: ArtifactType[]
  current_type?: ArtifactType
  completed_count?: number
  total_count?: number
  artifact_id?: string
  type?: ArtifactType
  title?: string
  body?: string
  type_specific_data?: Record<string, unknown>
  quality_score?: number
  quality_issues?: string[]
  error_code?: string | null
  retryable?: boolean
  artifacts?: ResourceArtifact[]
  aggregate_quality?: number
  mode?: 'bundle' | 'single'
  protocol_version?: 'learning-resource-bundle/v2'
  created_at?: string
  public_sources?: Array<SourceItem & { reference_id: string }>
}

export interface ModelSettings {
  provider: 'openai' | 'anthropic'
  base_url: string
  model_name: string
  api_key_configured: boolean
  api_key_hint: string
  anthropic_version: string
  request_timeout_seconds: number
}

export interface ModelConfigInput {
  provider: 'openai' | 'anthropic'
  api_key: string
  base_url: string
  model_name: string
  anthropic_version: string
  request_timeout_seconds: number
}

export interface ModelConnectionTest {
  provider: 'openai' | 'anthropic'
  model_name: string
  status: 'connected'
  latency_ms: number
}

export type ReasoningEffort = 'auto' | 'off' | 'low' | 'medium' | 'high' | 'xhigh'
export type ReasoningAdapter = 'none' | 'openai_reasoning_effort' | 'anthropic_thinking'

export interface ModelDefinition {
  id: string
  provider_model_name: string
  label: string
  max_output_tokens: number
  supported_reasoning_efforts: ReasoningEffort[]
  reasoning_adapter: ReasoningAdapter
}

export interface ModelProfileSummary {
  id: string
  label: string
  enabled: boolean
  provider: 'openai' | 'anthropic'
  base_url: string
  api_key_configured: boolean
  anthropic_version: string
  request_timeout_seconds: number
  default_model_id: string
  models: ModelDefinition[]
}

export interface ModelProfileInput extends Omit<ModelProfileSummary, 'api_key_configured'> {
  api_key: string
}

export interface ModelProfilePolicy {
  default_profile_id: string | null
  auto_failover: boolean
  fallback_profile_ids: string[]
}

export interface ModelProfileVault {
  version: 2
  global: ModelProfilePolicy
  profiles: ModelProfileSummary[]
}

export interface ModelRuntimeProfileStatus {
  profile_id: string
  enabled: boolean
  needs_attention: boolean
  circuit_state: 'closed' | 'open' | 'half_open'
  cooldown_until: number
  consecutive_failures: number
}

export interface ModelRuntimeStatus {
  ready: boolean
  default_profile_id: string | null
  auto_failover: boolean
  fallback_profile_ids: string[]
  profiles: ModelRuntimeProfileStatus[]
}

export interface ModelProfileMutationResult {
  vault: ModelProfileVault
  runtime: ModelRuntimeStatus
}

export interface SessionModelPreferenceInput {
  profile_mode: 'auto' | 'manual'
  preferred_profile_id: string | null
  model_id: string | null
  reasoning_effort: ReasoningEffort
  failover_override: 'inherit' | 'on' | 'off'
}

export interface SessionModelPreference extends SessionModelPreferenceInput {
  session_id: string
}

export type PetTaskState = 'idle' | 'running' | 'waiting' | 'review' | 'failed'
export type PetScale = 0.5 | 0.75 | 1 | 1.25 | 1.5
export type PetSpeed = 0.5 | 0.75 | 1 | 1.25 | 1.5 | 2

export interface PetSettings {
  visible: boolean
  scale: PetScale
  speed: PetSpeed
  soundEnabled: boolean
  soundVolume: PetVolume
  voiceEnabled: boolean
  voiceVolume: PetVolume
}

export type PetVolume = 0 | 0.25 | 0.5 | 0.75 | 1

export interface PetSummary {
  id: string
  displayName: string
  description: string
}

export interface PetSnapshot {
  available: boolean
  pet: PetSummary | null
  settings: PetSettings
  state: PetTaskState
}
