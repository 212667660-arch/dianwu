import type {
  ArtifactType,
  EvidenceStatus,
  KnowledgeBinding,
  KnowledgeImportJob,
  KnowledgePoint,
  ModelSettings,
  NextAction,
  QuestionItem,
  ReasoningEffort,
  ResourceArtifact,
  ResourceBundle,
  TextbookAccessMode,
  TextbookCatalogItem,
} from '@/api/types'

type Difficulty = QuestionItem['difficulty']
type Stage = TextbookCatalogItem['stage']
type Subject = TextbookCatalogItem['subject']
type Mastery = KnowledgePoint['mastery_label']
type BundleStatus = ResourceBundle['status']
type ArtifactStatus = ResourceArtifact['status']
type Provider = ModelSettings['provider']
type ImportStatus = KnowledgeImportJob['status']
type PrivacyMode = KnowledgeBinding['privacy_mode']
type NextActionCode = NextAction['action']

const keyFrom = <T extends string>(map: Record<T, string>) => (value: T): string => map[value]

export const difficultyKey = keyFrom<Difficulty>({ '\u57fa\u7840': 'statuses.difficulty.basic', '\u63d0\u9ad8': 'statuses.difficulty.advanced', '\u6311\u6218': 'statuses.difficulty.challenge' })
export const stageKey = keyFrom<Stage>({ '\u521d\u4e2d': 'statuses.stage.middleSchool', '\u9ad8\u4e2d': 'statuses.stage.highSchool' })
export const subjectKey = keyFrom<Subject>({ '\u6570\u5b66': 'statuses.subject.math' })
export const masteryKey = (value: Mastery): string => `statuses.mastery.${value}`
export const resourceTypeKey = keyFrom<ArtifactType>({ course_explanation: 'statuses.resourceType.courseExplanation', mind_map: 'statuses.resourceType.mindMap', question_bank: 'statuses.resourceType.questionBank', extended_reading: 'statuses.resourceType.extendedReading', adaptive_practice: 'statuses.resourceType.adaptivePractice' })
export const bundleStatusKey = (value: BundleStatus): string => `statuses.bundleStatus.${value}`
export const artifactStatusKey = (value: ArtifactStatus): string => `statuses.artifactStatus.${value}`
export const evidenceStatusKey = (value: EvidenceStatus): string => `statuses.evidenceStatus.${value}`
export const providerKey = (value: Provider): string => `statuses.provider.${value}`
export const reasoningEffortKey = (value: ReasoningEffort): string => `statuses.reasoningEffort.${value}`
export const importStatusKey = (value: ImportStatus): string => `statuses.importStatus.${value}`
export const accessModeKey = (value: TextbookAccessMode): string => `statuses.accessMode.${value}`
export const privacyModeKey = (value: PrivacyMode): string => `statuses.privacyMode.${value}`
export const nextActionKey = (value: NextActionCode): string => `statuses.nextAction.${value}`

const MASTERY_VALUES: ReadonlySet<string> = new Set(['WEAK', 'LEARNING', 'PROFICIENT', 'MASTERED'] satisfies Mastery[])
const NEXT_ACTION_VALUES: ReadonlySet<string> = new Set(['DIAGNOSE', 'REVIEW', 'START_PRACTICE', 'REMEDIATE', 'PRACTICE', 'CONSOLIDATE', 'CHALLENGE'] satisfies NextActionCode[])

export const isMastery = (value: string): value is Mastery => MASTERY_VALUES.has(value)
export const isNextAction = (value: string): value is NextActionCode => NEXT_ACTION_VALUES.has(value)
