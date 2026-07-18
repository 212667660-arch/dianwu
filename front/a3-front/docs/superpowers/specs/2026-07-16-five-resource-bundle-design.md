# Five Personalized Resource Types Design

## 1. Goal And Scope

Extend A3 from the existing `learning-resource/v1` note-and-practice output to a competition-ready resource system that can generate and display at least five distinct personalized learning resource types.

This scope includes:

- a default complete resource bundle;
- single-resource generation from the Smart Tutor composer;
- a planning agent and five specialized resource agents;
- structured persistence, streaming progress, partial success, retry, safety checks, and quality gates;
- desktop rendering for Markdown, safe Mermaid diagrams, question banks, readings, and adaptive practice tasks;
- backward compatibility with all existing v1 resources and databases.

This scope does not include course dataset import, image generation, video generation, or PPT file generation.

## 2. Resource Types

The fixed resource catalog is:

1. `course_explanation`: a course explanation document with learning objectives, core concepts, step-by-step explanations, common misconceptions, and personalized advice.
2. `mind_map`: a Mermaid `flowchart` or `graph` plus an equivalent hierarchical text outline.
3. `question_bank`: questions covering basic, intermediate, and challenge levels; every question includes an answer, explanation, and knowledge point.
4. `extended_reading`: further reading based on local knowledge and public sources when available. Citations use the existing `[资料N]` allowlist. When no reliable external source exists, the output explicitly states that no external source is attached.
5. `adaptive_practice`: a subject-adaptive practical task. Computer-related subjects receive a code lab with environment, starter code, steps, acceptance criteria, and reference approach. Other subjects receive an experiment, case analysis, or practical project with equivalent structure.

The default mode is `bundle`, which requests all five types. The `single` mode requests exactly one type.

## 3. Architecture

### 3.1 Planning Agent

The planning agent receives the validated learner profile, learning progress, mistakes, due reviews, local knowledge context, public-source snapshots, and the user's request. It produces one validated resource brief shared by all selected specialist agents.

The brief fixes the topic, learning objectives, target difficulty, weak knowledge points, style constraints, source allowlist, and subject category. It never contains secrets, local file paths, or untrusted instructions copied from source material.

### 3.2 Specialist Agents

Each resource type has a dedicated prompt builder and validator. In bundle mode, at most two specialist calls run concurrently after planning succeeds. In single mode, only the selected specialist runs.

Every specialist result is independently parsed, safety checked, citation sanitized, quality scored, and persisted into the in-progress bundle. One failed specialist does not invalidate successful siblings.

### 3.3 Aggregator

The aggregator orders validated artifacts according to the fixed catalog, builds readable Markdown for export and legacy surfaces, calculates bundle status and quality, and produces the structured payload used by the desktop renderer.

Bundle status values are:

- `COMPLETED`: every requested artifact succeeded;
- `PARTIAL`: at least one requested artifact succeeded and at least one failed;
- `FAILED`: planning failed or every requested artifact failed;
- `CANCELLED`: the user cancelled the generation.

## 4. Protocol And API Contract

The new protocol identifier is `learning-resource-bundle/v2`. `learning-resource/v1` remains supported for reading existing records and cached content.

Chat requests add two optional, fixed fields:

- `resource_mode`: `bundle` or `single`, defaulting to `bundle` after the learner profile is ready;
- `resource_type`: one catalog value, required only for `single` mode.

Electron IPC validation accepts only these fixed fields and enum values. Renderers cannot supply model profiles, backend addresses, tokens, file paths, source snapshots, or planner output.

The v2 bundle contains:

- bundle ID, protocol version, topic, profile version, learning-state version, mode, status, and requested types;
- ordered artifacts with type, title, status, Markdown body, type-specific structured data, quality score, quality issues, error code, and retryability;
- sanitized public and local knowledge source snapshots;
- aggregate quality and timestamps.

SSE adds structured events without removing existing events:

- `resource_plan`: the validated plan and requested type list without private context;
- `resource_progress`: current type, completed count, total count, and status;
- `resource_artifact`: one validated artifact or one safe artifact error;
- `resource_bundle`: the final structured bundle;
- existing `meta`, `sources`, `knowledge_sources`, `error`, `interrupted`, `persisted`, and `done` events retain their current meanings.

Non-streaming responses include the final bundle in an optional `resource_bundle` field. Existing clients that only read `reply` continue to receive the aggregate Markdown.

## 5. Persistence And Compatibility

The existing `resources.content` column stores canonical aggregate Markdown. A new nullable structured payload column stores canonical bundle JSON. `protocol_version` distinguishes v1 and v2. Existing v1 rows remain unchanged.

The startup migration adds only nullable or defaulted columns and is idempotent. No table rebuild or user-data reset is allowed.

Cache identity includes session, normalized request, resource mode, selected type, profile version, learning-state version, and knowledge context identity. A bundle cache entry can satisfy only the same bundle request. A single-resource cache entry can satisfy only the same resource type.

Retrying a failed artifact creates a new generation attempt for that artifact, then atomically replaces its failed entry in the bundle after validation. Successful sibling artifacts are immutable during the retry.

## 6. Cancellation, Failover, And Partial Failure

Bundle generation performs planning first, then runs specialist work with a concurrency limit of two. The existing generation owner, cancellation event, client-disconnect check, model routing, retry budget, circuit breaker, and stream interruption semantics remain authoritative.

Cancellation stops queued and running specialist work, preserves already validated artifacts as a cancelled partial bundle for inspection, and returns the session to its stable profiled state.

A model interruption never silently concatenates output from two profiles. The affected artifact records a safe interruption error and can use the existing explicit backup-continuation behavior.

Planning failure fails the whole bundle because specialists cannot safely infer independent constraints. Specialist failure produces `PARTIAL` when any sibling succeeds. Five specialist failures produce `FAILED`.

## 7. Quality And Content Safety

### 7.1 Shared Safety Gates

Before generation, requests are checked for explicit illegal, dangerous, privacy-invasive, credential-seeking, or disallowed sensitive instructions. Rejections use stable public error codes and do not call a model.

All agent prompts treat user text, public sources, and local documents as untrusted data. They prohibit instruction execution from sources, fabricated citations, secret or path disclosure, and unsupported certainty.

After generation, every artifact passes:

- schema and length validation;
- dangerous-content rule checks;
- source-reference allowlist sanitation;
- type-specific completeness checks;
- a minimum quality score.

### 7.2 Type-Specific Gates

- Course explanations require all five document sections and concrete topic content.
- Mind maps accept only Mermaid `flowchart` or `graph` syntax. HTML, script directives, initialization directives, external links, and click handlers are rejected. A valid text outline is always required.
- Question banks require all three difficulty levels and complete answer/explanation/knowledge-point fields.
- Extended reading may cite only supplied source IDs and must disclose when it has no external source.
- Adaptive practice requires objectives, prerequisites or environment, steps, acceptance criteria, and a reference approach. Code labs additionally require non-empty starter code.

## 8. Desktop Experience

The Smart Tutor composer receives a compact resource-type menu. Its options are Complete Resource Bundle and the five single types. Complete Resource Bundle is the default for profiled sessions.

During generation, the existing assistant response area shows stable progress rows for planning and each selected specialist. Completed artifacts appear as independent resource cards without shifting the composer layout.

Each card supports expand/collapse, copy Markdown, source inspection, quality status, and retry when failed. The mind-map card renders Mermaid with strict security settings and falls back to the required text outline on parsing or rendering failure.

Historical v1 assistant messages continue to render as text. V2 session resources use structured cards. On narrow screens, cards form one vertical column and controls wrap without horizontal scrolling.

No new top-level page or navigation item is introduced.

## 9. Testing Strategy

Backend tests cover:

- v2 models, parser/serializer round trips, enum rejection, and v1 compatibility;
- planning and five specialist prompt contracts;
- subject-adaptive practical-task classification;
- Mermaid safety, question difficulty coverage, citation sanitation, content safety, and all quality gates;
- bundle, single, partial success, total failure, retry, cancellation, disconnect, failover, and cache isolation;
- SQLite migration and restoration of existing sessions;
- HTTP and SSE contracts, including bounded structured payloads.

Frontend and Electron tests cover:

- composer selection and request payloads;
- bundle progress and five resource card renderers;
- Mermaid strict rendering and outline fallback;
- copy, source inspection, failed-artifact retry, old-resource rendering, and session switching;
- mobile-width layout behavior;
- preload and IPC field allowlists.

Release verification requires the full backend suite, Electron Node suite, Vitest suite, desktop build, unpacked packaging, isolated-userData startup and exit, encrypted-profile bootstrap, and zero residual A3 processes.

## 10. Acceptance Criteria

The feature is accepted when:

1. a default profiled-session request generates and displays all five resource types;
2. single mode generates only the selected type;
3. each artifact is independently validated and scored;
4. one failed specialist preserves successful siblings and offers a scoped retry;
5. invalid Mermaid never executes and always falls back to text;
6. fabricated source IDs are removed or rejected;
7. existing v1 resources and databases open without manual migration;
8. cancellation and disconnection leave the session and process tree clean;
9. automated and packaged desktop verification passes;
10. project documentation maps the five implemented resource types to the A3 competition requirement.
