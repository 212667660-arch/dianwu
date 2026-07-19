import { bytesToHex } from '@noble/hashes/utils'
import { sha256 } from '@noble/hashes/sha256'
import { NodeTypes, parse as parseTemplate, type RootNode, type TemplateChildNode } from '@vue/compiler-dom'
import { parse as parseSfc } from '@vue/compiler-sfc'
import ts from 'typescript'

export type CandidateKind =
  | 'string_literal'
  | 'no_substitution_template_literal'
  | 'template_expression'
  | 'vue_text'
  | 'vue_static_attribute'

export interface SourceCandidate {
  id: string
  source: string
  kind: CandidateKind
  raw: string
  expressions: string[]
  line: number
  column: number
}

export const CLASSIFIED_REASONS = ['not_user_visible', 'developer_diagnostic', 'proper_noun', 'external_protocol'] as const
export type ClassifiedReason = typeof CLASSIFIED_REASONS[number]

export type InventoryEntry =
  | { id: string; mode: 'mapped'; catalog_key: string; template: string; expression_placeholders: string[] }
  | { id: string; mode: 'classified'; reason: ClassifiedReason }

export interface InventoryIssue { id: string; code: 'duplicate_entry' | 'invalid_reason' | 'expression_mismatch' | 'template_mismatch' | 'missing_catalog_key' | 'catalog_placeholder_mismatch' }

export interface InventoryValidation {
  missing: SourceCandidate[]
  extra: InventoryEntry[]
  issues: InventoryIssue[]
}

const HAN = /\p{Script=Han}/u
const STATIC_ATTRIBUTES = new Set(['aria-label', 'aria-description', 'title', 'placeholder'])

export function shouldScanSource(path: string): boolean {
  const normalized = path.replaceAll('\\', '/')
  return /\.(?:vue|ts|tsx|js|jsx|mjs|cjs)$/.test(normalized)
    && !/(?:^|\/)(?:dist|release|generated|locales)(?:\/|$)/.test(normalized)
    && !/(?:^|\/)(?:tests?|__tests__)(?:\/|$)/.test(normalized)
    && !/\.(?:test|spec)\.[^/]+$/.test(normalized)
}

function digest(value: string): string {
  return bytesToHex(sha256(new TextEncoder().encode(value))).slice(0, 24)
}

function makeCandidate(source: string, kind: CandidateKind, raw: string, expressions: string[], line: number, column: number): SourceCandidate | undefined {
  const normalized = raw.replace(/\s+/g, ' ').trim()
  if (!HAN.test(normalized)) return undefined
  return {
    id: digest([source, kind, line, column, normalized].join('\0')),
    source,
    kind,
    raw: normalized,
    expressions,
    line,
    column,
  }
}

function scriptKind(path: string): ts.ScriptKind {
  if (/\.tsx$/.test(path)) return ts.ScriptKind.TSX
  if (/\.jsx?$/.test(path)) return ts.ScriptKind.JSX
  return ts.ScriptKind.TS
}

function extractScript(source: string, text: string, offsetLine = 0, offsetColumn = 0): SourceCandidate[] {
  const file = ts.createSourceFile(source, text, ts.ScriptTarget.Latest, true, scriptKind(source))
  const result: SourceCandidate[] = []
  const add = (node: ts.Node, kind: CandidateKind, raw: string, expressions: string[]) => {
    const start = node.getStart(file)
    const position = file.getLineAndCharacterOfPosition(start)
    const line = position.line + 1 + offsetLine
    const column = position.character + 1 + (position.line === 0 ? offsetColumn : 0)
    const candidate = makeCandidate(source, kind, raw, expressions, line, column)
    if (candidate) result.push(candidate)
  }
  const visit = (node: ts.Node): void => {
    if (ts.isStringLiteral(node)) {
      if (!ts.isImportDeclaration(node.parent) && !ts.isExportDeclaration(node.parent)
        && !(ts.isPropertyAssignment(node.parent) && node.parent.name === node)
        && !(ts.isPropertySignature(node.parent) && node.parent.name === node)
        && !(ts.isElementAccessExpression(node.parent) && node.parent.argumentExpression === node)) {
        add(node, 'string_literal', node.text, [])
      }
    } else if (ts.isNoSubstitutionTemplateLiteral(node)) {
      add(node, 'no_substitution_template_literal', node.text, [])
    } else if (ts.isTemplateExpression(node)) {
      const expressions = node.templateSpans.map(span => span.expression.getText(file))
      add(node, 'template_expression', node.getText(file).slice(1, -1), expressions)
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  return result
}

function walkVueTemplate(source: string, root: RootNode, lineOffset: number): SourceCandidate[] {
  const result: SourceCandidate[] = []
  const add = (kind: CandidateKind, raw: string, expressions: string[], line: number, column: number) => {
    const candidate = makeCandidate(source, kind, raw, expressions, line + lineOffset, column)
    if (candidate) result.push(candidate)
  }
  const visit = (node: RootNode | TemplateChildNode): void => {
    if (node.type === NodeTypes.TEXT) add('vue_text', node.content, [], node.loc.start.line, node.loc.start.column)
    if (node.type === NodeTypes.INTERPOLATION) {
      result.push(...extractScript(source, node.content.loc.source, node.content.loc.start.line - 1 + lineOffset, node.content.loc.start.column - 1))
    }
    if (node.type === NodeTypes.ELEMENT) {
      for (const prop of node.props) {
        if (prop.type === NodeTypes.ATTRIBUTE && prop.value && STATIC_ATTRIBUTES.has(prop.name)) {
          add('vue_static_attribute', prop.value.content, [], prop.value.loc.start.line, prop.value.loc.start.column)
        } else if (prop.type === NodeTypes.DIRECTIVE && prop.exp) {
          result.push(...extractScript(source, prop.exp.loc.source, prop.exp.loc.start.line - 1 + lineOffset, prop.exp.loc.start.column - 1))
        }
      }
      for (const child of node.children) visit(child)
    } else if (node.type === NodeTypes.ROOT) {
      for (const child of node.children) visit(child)
    } else if (node.type === NodeTypes.IF) {
      for (const branch of node.branches) for (const child of branch.children) visit(child)
    } else if (node.type === NodeTypes.FOR) {
      for (const child of node.children) visit(child)
    }
  }
  visit(root)
  return result
}

export function extractSourceCandidates(source: string, text: string): SourceCandidate[] {
  if (!shouldScanSource(source)) return []
  if (!source.endsWith('.vue')) return extractScript(source, text)
  const { descriptor } = parseSfc(text, { filename: source })
  const result: SourceCandidate[] = []
  if (descriptor.template) result.push(...walkVueTemplate(source, parseTemplate(descriptor.template.content), descriptor.template.loc.start.line - 1))
  for (const block of [descriptor.script, descriptor.scriptSetup]) {
    if (block) result.push(...extractScript(source, block.content, block.loc.start.line - 1))
  }
  return result.sort((left, right) => left.line - right.line || left.column - right.column || left.id.localeCompare(right.id))
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map(match => match[1])
}

export function validateInventory(candidates: SourceCandidate[], entries: InventoryEntry[], catalog: Record<string, string>): InventoryValidation {
  const candidateById = new Map(candidates.map(candidate => [candidate.id, candidate]))
  const entryById = new Map<string, InventoryEntry>()
  const issues: InventoryIssue[] = []
  for (const entry of entries) {
    if (entryById.has(entry.id)) issues.push({ id: entry.id, code: 'duplicate_entry' })
    else entryById.set(entry.id, entry)
  }
  const missing = candidates.filter(candidate => !entryById.has(candidate.id))
  const extra = entries.filter(entry => !candidateById.has(entry.id))
  for (const [id, entry] of entryById) {
    const candidate = candidateById.get(id)
    if (!candidate) continue
    if (entry.mode === 'classified') {
      if (!(CLASSIFIED_REASONS as readonly string[]).includes(entry.reason)) issues.push({ id, code: 'invalid_reason' })
      continue
    }
    if (entry.expression_placeholders.length !== candidate.expressions.length
      || entry.expression_placeholders.some((name, index) => name !== candidate.expressions[index])) issues.push({ id, code: 'expression_mismatch' })
    if (placeholders(entry.template).join('\0') !== entry.expression_placeholders.join('\0')) issues.push({ id, code: 'template_mismatch' })
    const message = catalog[entry.catalog_key]
    if (message === undefined) issues.push({ id, code: 'missing_catalog_key' })
    else if (placeholders(message).join('\0') !== entry.expression_placeholders.join('\0')) issues.push({ id, code: 'catalog_placeholder_mismatch' })
  }
  return { missing, extra, issues }
}
