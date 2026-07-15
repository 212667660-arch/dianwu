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
export interface KnowledgeImportJob { id: number; document_id: number; status: string; progress: number; stage: string; retryable: boolean; safe_error_code: string | null; cancel_requested: boolean; version: number; created_at: string; updated_at: string }
export interface KnowledgeBinding { session_id: string; collection_ids: number[]; privacy_mode: 'allow_model_context' | 'local_search_only' }
export interface KnowledgeImportBatch { jobs: KnowledgeImportJob[] }
export interface KnowledgeSearchResult { mode: 'keyword' | 'hybrid'; items: Array<{ chunk_id: number; document_id: number; document_name: string; text: string; heading_path: string; locator: KnowledgeLocator; score: number; retrieval_mode: 'keyword' | 'hybrid' }> }

export interface ChatResponse {
  reply: string
  phase: 'diagnosis' | 'profile' | 'resource'
  state: string
  profile_version: number
  cached: boolean
  sources: SourceItem[]
  knowledge_sources: KnowledgeSource[]
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
  sources?: SourceItem[]
  knowledge_sources?: KnowledgeSource[]
  resource_id?: number
  profile_version?: number
  cached?: boolean
  provisional?: boolean
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
