# BreakingWeb Human Recording Assignment Plan v1

This file summarizes the task assignment generated from `breakingweb_human_panel_v2_140.yaml`.

The full BreakingWeb benchmark currently has **519 base tasks** across 7 sandbox websites
(full agent evaluation = 519 × 2 = 1038 task-conditions). The human plan covers a curated
140-base-task panel — 4 base tasks per environment × difficulty cell.

## Interpretation

- The primary panel contains **140 base tasks**.
- Each base task has **2 task-conditions**: `clean` and `intervention`.
- Each assigned task-condition is recorded twice by the same annotator: `cold` then `warm`.
- Therefore the primary workload is **140 × 2 task-conditions × 2 attempts = 560 attempts**.
- The **lightweight duplicate-human stability audit** contains **35 duplicated task-conditions**, not 35 base tasks (one duplicated task-condition in every environment × difficulty cell). Each duplicated task-condition is recorded `cold` and `warm` by a second independent annotator, giving **35 × 2 = 70 attempts**.
- Total expected recorded attempts: **630**.


## Primary full-load annotators

| Annotator | Primary task-conditions | Attempts | Clean | Intervention | Env portfolio | Difficulty balance |
|---|---:|---:|---:|---:|---|---|
| P1 | 70 | 140 | 35 | 35 | amazon: 20, booking: 10, lms: 20, reddit: 20 | easy: 14, medium: 14, hard: 14, expert: 14, frontier: 14 |
| P2 | 70 | 140 | 35 | 35 | booking: 15, gmail: 15, reddit: 20, robinhood: 20 | easy: 14, medium: 14, hard: 14, expert: 14, frontier: 14 |
| P3 | 70 | 140 | 35 | 35 | booking: 15, gmail: 15, patient_portal: 20, robinhood: 20 | easy: 14, medium: 14, hard: 14, expert: 14, frontier: 14 |
| P4 | 70 | 140 | 35 | 35 | amazon: 20, gmail: 10, lms: 20, patient_portal: 20 | easy: 14, medium: 14, hard: 14, expert: 14, frontier: 14 |

Each full-load annotator has exactly **70 primary task-conditions**, exactly **35 clean + 35 intervention**, and exactly **14 task-conditions per difficulty**. This also gives exactly **7 clean and 7 intervention task-conditions at every difficulty** for each full-load annotator.


## Primary environment portfolios

| Environment | Primary annotators | Split |
|---|---|---|
| amazon | P4, P1 | P4: 20, P1: 20 |
| booking | P2, P3, P1 | P2: 15, P3: 15, P1: 10 |
| gmail | P3, P2, P4 | P3: 15, P2: 15, P4: 10 |
| lms | P4, P1 | P4: 20, P1: 20 |
| patient_portal | P3, P4 | P3: 20, P4: 20 |
| reddit | P1, P2 | P1: 20, P2: 20 |
| robinhood | P2, P3 | P2: 20, P3: 20 |


## Limited-load duplicate annotators

| Annotator | Duplicate task-conditions | Attempts | Clean | Intervention | Difficulty balance | Environments |
|---|---:|---:|---:|---:|---|---|
| D1 | 9 | 18 | 4 | 5 | easy: 2, medium: 2, hard: 1, expert: 2, frontier: 2 | amazon: 1, booking: 1, gmail: 1, lms: 1, patient_portal: 1, reddit: 2, robinhood: 2 |
| D2 | 9 | 18 | 4 | 5 | easy: 2, medium: 2, hard: 2, expert: 1, frontier: 2 | amazon: 1, booking: 1, gmail: 2, lms: 2, patient_portal: 1, reddit: 1, robinhood: 1 |
| D3 | 9 | 18 | 5 | 4 | easy: 2, medium: 2, hard: 2, expert: 2, frontier: 1 | amazon: 1, booking: 2, gmail: 1, lms: 1, patient_portal: 2, reddit: 1, robinhood: 1 |
| D4 | 8 | 16 | 4 | 4 | easy: 1, medium: 1, hard: 2, expert: 2, frontier: 2 | amazon: 2, booking: 1, gmail: 1, lms: 1, patient_portal: 1, reddit: 1, robinhood: 1 |

Each limited-load annotator gets at least one duplicate task-condition from every environment. The duplicate subset is for estimating human-reference stability and task ambiguity, not for changing the primary reference unless adjudication finds a shorter valid warm trace.


## Script integration recommendation

The assignment YAML has three task lists:

1. `condition_assignments`: 280 primary task-condition assignments.
2. `duplicate_condition_assignments`: 35 second-human duplicate assignments.
3. `base_task_assignments`: 140 base-task summaries showing the clean and intervention primary annotators.

For the launcher, implement this logic:

```python
name = input_name.strip().lower()
eligible = [a for a in condition_assignments + duplicate_condition_assignments
            if a['annotator'].lower() == name]
show eligible sorted by annotators[name]['recommended_order_assignment_ids']
for each assignment, run the same task-condition twice: attempt='cold' then attempt='warm'
save under: traces/{annotator}/{assignment_role}/{env}/{base_task_id}/{condition}/{attempt}/
```

The `condition` field determines whether the script launches the clean task or the official intervention variant. If `condition == 'intervention'`, use `official_intervention_variant.variant_id` and `official_intervention_variant.variant_yaml`. If `condition == 'clean'`, launch with no intervention variant.


## Assignment files

- Machine-readable assignment: `assignments_v1.yaml`
- Flat CSV inspection file: `assignments_v1_flat.csv`
- Panel reference: `panel_v2_140.yaml`
- Experimental design report: `trace_experiment_report.md`
