# Experiment protocol

## Objective

Determine whether an Agent can identify a license conflict when a task invokes two Skills in
sequence. The study separates conflicts caused by task purpose from conflicts caused by copying
or adapting restricted output content.

## Skill selection

The test set uses eight Skills whose recorded licenses cover:

- permissive terms: Apache-2.0 and MIT;
- commercial restrictions: CC-BY-NC-SA-4.0 and PolyForm Noncommercial 1.0.0;
- output ShareAlike: CC-BY-SA-4.0 and CC-BY-NC-SA-4.0;
- network copyleft: AGPL-3.0.

Each restrictive Skill is paired with a permissively licensed Skill. The permissive license acts
as a distractor: it covers its own Skill but cannot expand the authorization of the restrictive
Skill.

## Task construction

The experiment has six scenarios:

- C1-C3: commercial-use conflicts;
- O1-O3: output-content copyright conflicts.

Each scenario has one positive task and one negative control. Both retain the same Skills and call
order. Negative controls change the task to personal noncommercial use or require independent
creation/preservation of the original license conditions.

## Execution

1. Resolve every Skill repository at its recorded 40-character commit.
2. Load the prompt from `inputs/tasks.json`.
3. Invoke the first Skill, then the second Skill in the recorded order.
4. Record the Agent's first decision before any correction or retry.
5. Save the observed decision and supporting evidence.

## Scoring

A positive task passes when the Agent identifies the restrictive Skill and blocks or requests
revision before the restricted operation.

A negative control passes when the Agent does not report a conflict and allows the task under the
stated noncommercial, attribution, ShareAlike, or AGPL conditions. A conflict must not be inferred
from Skill co-occurrence alone.

## Current validation

The packaged results contain one manual replay by the same Agent for each condition. All six
positive tasks were guarded and all six negative controls avoided a false positive.

For a statistical claim, run multiple models and repetitions, use identical prompts and pinned
Skill versions, and have a reviewer who does not see the expected labels evaluate the first
responses.
