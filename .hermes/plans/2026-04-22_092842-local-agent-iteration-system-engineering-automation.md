# Local Agent Iteration System (Hermes + Evolver) Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to implement this plan task-by-task, with a fresh subagent for each task and explicit review gates.

**Goal:** Turn this workspace into a durable local agent iteration system that captures run evidence, distills lessons, and reuses those lessons automatically in future agent runs.

**Architecture:**
- Hermes remains the execution layer: it runs tasks, records context, and exposes tools.
- LCM remains the memory/trace layer: it stores verbatim history, summaries, and retrieval tools.
- Evolver becomes the post-run adaptation layer: it reads run evidence, generates improvement guidance, and helps convert repeated patterns into reusable assets.
- Automation ties the loop together: failure-triggered postmortems and scheduled review jobs turn ad hoc improvements into a continuous cycle.

**Tech Stack:** Python, existing Hermes CLI/runtime, LCM plugin (`plugins/context_engine/lcm/`), task tooling (`tools/`, `cronjob`, `delegate_task`), Git, optional Evolver CLI (`evolver`), and pytest.

---

## Current Context / Assumptions

- This repo is the Hermes agent workspace.
- The current codebase already has:
  - persistent memory
  - session search
  - skill management
  - a context engine / LCM subsystem
  - cronjob scheduling
  - subagent delegation
- Evolver is best treated as an optional local dependency that improves the system around Hermes, not as a hard dependency for core execution.
- The target is **one project at a time first**, then reusable across projects.

---

## Proposed Approach

1. Add a lightweight run-evidence schema so every meaningful agent session can produce a normalized record.
2. Add an experience distillation step that converts repeated failures/successes into compact “lessons” and candidate reusable rules.
3. Add a small Evolver bridge so Hermes can invoke Evolver locally after failures, on demand, or in scheduled review mode.
4. Add automation so the system can run in a nightly / post-failure loop without manual prompting.
5. Add tests and guardrails so the loop is safe, deterministic, and doesn’t spam memory with low-value noise.

---

## Step-by-Step Plan

### Task 1: Define the local iteration record format

**Objective:** Create a stable schema for recording what happened in a run, what failed, what changed, and what lesson was learned.

**Files:**
- Create: `plugins/context_engine/lcm/iteration_schema.py`
- Modify: `plugins/context_engine/lcm/__init__.py`
- Modify: `tests/plugins/test_iteration_schema.py`

**Step 1: Write failing tests**

Add tests for:
- minimal event payload validation
- required fields (`session_id`, `project_root`, `status`, `signals`, `summary`)
- optional fields (`git_commit`, `failed_tests`, `lesson`, `next_action`, `artifact_refs`)
- serialization / round-trip stability

**Step 2: Minimal implementation**

Implement a small dataclass or typed dict that can:
- normalize the input fields
- produce JSON-safe output
- reject empty / malformed records

**Step 3: Verification**

Run:
```bash
pytest tests/plugins/test_iteration_schema.py -v
```
Expected: all tests pass.

---

### Task 2: Capture run evidence automatically at session end

**Objective:** Record the evidence needed for later review without relying on manual notes.

**Files:**
- Modify: `run_agent.py`
- Modify: `plugins/context_engine/lcm/engine.py`
- Modify: `plugins/context_engine/lcm/store.py`
- Modify: `tests/run_agent/test_compression_persistence.py`
- Modify: `tests/run_agent/test_run_agent.py`

**Step 1: Write failing tests**

Add coverage for:
- session-end hook emits one iteration record when a run completes
- failed runs include failure signals and relevant test output
- successful runs include summary and “what worked” notes
- the capture path is skipped for ignored/stateless sessions

**Step 2: Implement capture hook**

Hook the existing agent lifecycle so that, at the end of a run, the system persists:
- the project path
- git state / commit hash if available
- top-level success/failure status
- extracted error signatures
- a short summary of what changed

Keep capture lightweight and non-blocking.

**Step 3: Verification**

Run:
```bash
pytest tests/run_agent/test_run_agent.py tests/run_agent/test_compression_persistence.py -v
```
Expected: new capture behavior passes without changing core context compression semantics.

---

### Task 3: Add lesson distillation for repeated failures

**Objective:** Convert repeated signals into reusable lessons rather than raw logs.

**Files:**
- Create: `plugins/context_engine/lcm/lesson_distiller.py`
- Modify: `plugins/context_engine/lcm/engine.py`
- Modify: `plugins/context_engine/lcm/schemas.py`
- Modify: `tests/plugins/test_lesson_distiller.py`

**Step 1: Write failing tests**

Cover scenarios such as:
- repeated same-root failure becomes one lesson
- different failures stay separate
- lessons are concise and action-oriented
- lessons reference evidence, but do not duplicate full logs

**Step 2: Implement distillation**

Build a reducer that takes recent iteration records and emits:
- `lesson`
- `trigger`
- `confidence`
- `evidence_refs`
- `recommended_next_action`

Prefer simple deterministic heuristics first; keep the model/LLM call optional.

**Step 3: Verification**

Run:
```bash
pytest tests/plugins/test_lesson_distiller.py -v
```
Expected: deterministic lessons are stable and deduplicated.

---

### Task 4: Add an Evolver bridge for post-run review

**Objective:** Let Hermes call Evolver as an optional local reviewer that turns run evidence into improvement guidance.

**Files:**
- Create: `plugins/context_engine/lcm/evolver_bridge.py`
- Modify: `run_agent.py`
- Modify: `hermes_cli/config.py`
- Modify: `tests/run_agent/test_plugin_context_engine_init.py`
- Create: `tests/plugins/test_evolver_bridge.py`

**Step 1: Write failing tests**

Cover:
- Evolver bridge disabled by default
- when enabled, it locates the local `evolver` binary or configured path
- it can pass a run bundle / evidence path to Evolver
- failures to invoke Evolver are non-fatal and logged

**Step 2: Implement bridge**

Use a conservative contract:
- input: run evidence bundle or path to evidence directory
- output: structured review result or plain-text guidance
- behavior: optional and failure-tolerant

Avoid making the main agent depend on Evolver at runtime.

**Step 3: Verification**

Run:
```bash
pytest tests/plugins/test_evolver_bridge.py tests/run_agent/test_plugin_context_engine_init.py -v
```
Expected: bridge is off by default; enabling it does not break agent init.

---

### Task 5: Wire automation for failure-triggered and scheduled reviews

**Objective:** Make iteration continuous by adding automatic review jobs.

**Files:**
- Modify: `toolsets.py`
- Create: `tools/evolver_review_tool.py`
- Modify: `tools/__init__.py` or tool registry file if needed
- Create: `tests/tools/test_evolver_review_tool.py`
- Create: `.hermes/plans/` docs only if the automation requires usage notes

**Step 1: Write failing tests**

Cover:
- tool can queue a review job from a path or session id
- tool rejects missing/invalid evidence inputs
- tool does not run Evolver directly unless explicitly configured

**Step 2: Implement tool + cron hooks**

Add a small tool that can:
- create a review request
- route it to a scheduled cronjob or immediate local review
- attach the resulting lesson to memory / session notes

Suggested automation modes:
- **post-failure:** run immediately when a session ends in failure
- **nightly:** run once per day over the last N sessions
- **manual:** user triggers review on demand

**Step 3: Verification**

Run:
```bash
pytest tests/tools/test_evolver_review_tool.py -v
```
Then verify a dry-run scheduling path using existing cronjob tooling.

---

### Task 6: Add a promotion path from lesson to reusable asset

**Objective:** Promote high-value lessons into durable skills / prompts / presets.

**Files:**
- Modify: `skills/` workflow if applicable
- Modify: `skill_manage` usage docs or a repo doc under `docs/`
- Create: `tests/plugins/test_lesson_promotion.py`

**Step 1: Write failing tests**

Validate that:
- only high-confidence lessons can be promoted
- promoted content is concise and reusable
- duplicates are not re-filed

**Step 2: Implement promotion policy**

Promotion should be explicit and conservative:
- lessons become skills only after repeated validation
- one-off noise stays in run evidence, not the skill library
- a human approval step is available for sensitive promotions

**Step 3: Verification**

Run:
```bash
pytest tests/plugins/test_lesson_promotion.py -v
```
Expected: only validated lessons can be promoted.

---

### Task 7: End-to-end validation and operator docs

**Objective:** Prove the loop works and document how to use it.

**Files:**
- Modify: `README.md` or a dedicated doc under `docs/`
- Create: `docs/local-agent-iteration-system.md`
- Modify: `.github/` only if CI needs new test coverage

**Step 1: Add integration test(s)**

Add one end-to-end test that simulates:
- a failed run
- evidence capture
- distillation
- optional Evolver review
- scheduled or manual review output

**Step 2: Document operator workflow**

Document:
- how to enable the bridge
- where evidence is stored
- how to trigger review manually
- how to inspect lessons
- how to roll back or disable automation

**Step 3: Verification**

Run the focused test suite and one broader smoke run:
```bash
pytest tests/run_agent tests/plugins tests/tools -v
```
Expected: all new functionality passes and the current agent behavior is unchanged by default.

---

## Automation Design Rules

- Default to **opt-in** for Evolver invocation.
- Never let automation mutate source code without an explicit human gate.
- Treat failure logs as evidence, not truth — distill, don’t blindly memorize.
- Keep promotion thresholds high to avoid contaminating the skill library.
- Prefer local filesystem + git state over network dependencies.
- If Evolver is missing, the system should degrade gracefully and still keep operating.

---

## Risks / Tradeoffs

- **Noise risk:** too many low-value lessons can pollute the memory system.
- **Tight coupling risk:** making Evolver mandatory would hurt portability.
- **Automation risk:** scheduled jobs can become background clutter if not rate-limited.
- **False confidence risk:** repeated failures can look like a pattern when they are actually unrelated.
- **Maintenance risk:** any new bridge should have a clean off-switch.

Mitigation:
- confidence thresholds
- deduplication
- manual approval for promotion
- dry-run modes
- explicit config flags

---

## Suggested Config Flags

Add config defaults such as:
- `EVOLVER_ENABLED=false`
- `EVOLVER_PATH=evolver`
- `EVOLVER_POST_RUN_REVIEW=false`
- `EVOLVER_NIGHTLY_REVIEW=false`
- `EVOLVER_PROMOTION_THRESHOLD=0.85`
- `EVOLVER_REVIEW_LOOKBACK=20`

---

## Suggested Rollout Order

1. Schema + evidence capture
2. Lesson distillation
3. Optional Evolver bridge
4. Automation / cron
5. Promotion to reusable assets
6. Documentation + full smoke test

---

## Success Criteria

The system is done when:
- every meaningful run emits a structured iteration record
- repeated failures produce concise, reusable lessons
- Evolver can be invoked locally as an optional reviewer
- scheduled reviews run without manual babysitting
- high-value lessons can be promoted into durable agent assets
- the whole loop is off by default and safe to disable
