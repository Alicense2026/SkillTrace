# Data dictionary

## inputs/skills.json

- `id`: stable local Skill identifier.
- `name`: display name used in the experiment.
- `repository`: GitHub `owner/repository`.
- `commit`: exact 40-character Git commit.
- `skill_path`: path to the selected `SKILL.md`.
- `license`: normalized license label used for the experiment.
- `evidence`: human-readable list of license evidence locations.

## inputs/tasks.json

- `run_id`: paired task identifier such as `C1-P` or `C1-N`.
- `scenario`: `C1`-`C3` or `O1`-`O3`.
- `condition`: `positive` or `negative_control`.
- `call_order`: ordered Skill names passed to the Agent.
- `task`: short description of the scenario.
- `prompt`: exact task prompt used for the replay.
- `expected`: expected conflict and guard behavior.
- `observed`: first decision and response recorded after execution.
- `evidence`: license and artifact evidence used for the decision.
- `pass`: whether the first decision matched the expected behavior.

## outputs/results.json

- `metadata`: experiment date, execution mode, and design normalization.
- `skills`: complete Skill manifest.
- `runs`: the 12 detailed run records.
- `summary`: positive, negative-control, and overall pass totals.

## Decision labels

- `blocked_before_restricted_call`: stopped before invoking the restrictive step.
- `blocked_before_delivery`: stopped before delivering a restricted artifact.
- `blocked_before_packaging`: stopped before repackaging restricted material.
- `requested_revision`: the original request was noncompliant, but a compliant revision remains
  possible.
- `allowed_with_conditions`: no conflict at the tested boundary; relevant license conditions
  still apply.

A blocked positive task is a successful experiment outcome. "Pass" evaluates the Agent's
compliance decision, not whether the originally requested commercial or proprietary artifact was
completed.
