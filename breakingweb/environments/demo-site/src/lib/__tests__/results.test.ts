import { describe, it, expect } from "vitest";
import { normalizeTrajectoryData } from "../results";
import type { TrajectoryData, TrajectoryStep } from "../results";

/* ------------------------------------------------------------------ */
/*  Category 8: normalizeTrajectoryData unit tests                     */
/* ------------------------------------------------------------------ */

function makeStep(overrides: Partial<TrajectoryStep> = {}): TrajectoryStep {
  return {
    step: 0,
    thought: "thinking...",
    action: { action: "click", ref: 1 },
    targets: {},
    status: "success",
    elapsed_seconds: 1.5,
    ...overrides,
  };
}

function makeTrajectoryData(overrides: Partial<TrajectoryData> = {}): TrajectoryData {
  return {
    task_id: "test_task",
    title: "Test Task",
    instruction: "Do something",
    difficulty: "easy",
    model: "gpt-4o",
    total_steps: 2,
    elapsed_seconds: 5.0,
    completed: true,
    start_path: "/inbox?label=inbox",
    evaluation: {
      score: 0.8,
      success: true,
      reasoning: "Good job",
      criteria_results: [{ desc: "Did the thing", passed: true }],
    },
    steps: [makeStep({ step: 0 }), makeStep({ step: 1, elapsed_seconds: 3.0 })],
    ...overrides,
  };
}

describe("normalizeTrajectoryData", () => {
  // 8a: Returns null for null payload
  it("returns null for null payload", () => {
    expect(normalizeTrajectoryData("task_1", null)).toBeNull();
  });

  // 8b: Normalizes bare array of steps into full TrajectoryData
  it("normalizes bare array of steps into full TrajectoryData", () => {
    const steps: TrajectoryStep[] = [
      makeStep({ step: 0, elapsed_seconds: 1.0 }),
      makeStep({ step: 1, elapsed_seconds: 3.0 }),
    ];

    const result = normalizeTrajectoryData("my_task", steps);
    expect(result).not.toBeNull();
    expect(result!.task_id).toBe("my_task");
    expect(result!.title).toBe("my_task");
    expect(result!.total_steps).toBe(2);
    expect(result!.elapsed_seconds).toBe(3.0);
    expect(result!.evaluation.score).toBe(0);
    expect(result!.evaluation.success).toBe(false);
    expect(result!.start_path).toBe("/inbox?label=inbox");
  });

  // 8c: Normalizes full payload, filling missing fields with defaults
  it("fills missing fields with defaults on full payload", () => {
    const payload = {
      task_id: "t1",
      title: "T1",
      instruction: "do it",
      difficulty: "hard",
      model: "gpt-4o",
      steps: [makeStep()],
    } as unknown as TrajectoryData;

    const result = normalizeTrajectoryData("t1", payload);
    expect(result).not.toBeNull();
    expect(result!.total_steps).toBe(1);
    expect(result!.elapsed_seconds).toBe(0);
    expect(result!.start_path).toBe("/inbox?label=inbox");
    expect(result!.evaluation.score).toBe(0);
    expect(result!.evaluation.success).toBe(false);
    expect(result!.evaluation.reasoning).toBe("");
    expect(result!.evaluation.criteria_results).toEqual([]);
  });

  // 8d: normalizeTargets wraps flat target object into { ref: ... }
  it("wraps flat target with role/name into { ref: target }", () => {
    const steps: TrajectoryStep[] = [
      makeStep({
        targets: { role: "button", name: "Save" } as unknown as TrajectoryStep["targets"],
      }),
    ];

    const result = normalizeTrajectoryData("t1", steps);
    expect(result!.steps[0].targets.ref).toEqual({ role: "button", name: "Save" });
  });

  // 8e: normalizeTargets passes through ref/from_ref/to_ref structure
  it("passes through structured ref/from_ref/to_ref targets", () => {
    const targets = {
      ref: { role: "button", name: "OK" },
      from_ref: { role: "textbox", name: "Search" },
    };
    const steps: TrajectoryStep[] = [makeStep({ targets })];

    const result = normalizeTrajectoryData("t1", steps);
    expect(result!.steps[0].targets.ref).toEqual({ role: "button", name: "OK" });
    expect(result!.steps[0].targets.from_ref).toEqual({ role: "textbox", name: "Search" });
  });

  // 8f: normalizeTargets returns {} for null/undefined input
  it("returns empty targets for null/undefined target input", () => {
    const steps: TrajectoryStep[] = [
      makeStep({ targets: null as unknown as TrajectoryStep["targets"] }),
    ];

    const result = normalizeTrajectoryData("t1", steps);
    expect(result!.steps[0].targets).toEqual({});
  });

  // 8g: Fills default replay_path and result_path per step
  it("fills default replay_path and result_path on steps", () => {
    const steps: TrajectoryStep[] = [makeStep()];
    const result = normalizeTrajectoryData("t1", steps);
    expect(result!.steps[0].replay_path).toBe("/inbox?label=inbox");
    expect(result!.steps[0].result_path).toBe("/inbox?label=inbox");
  });

  it("preserves explicit replay_path and result_path", () => {
    const steps: TrajectoryStep[] = [
      makeStep({
        replay_path: "/thread/abc",
        result_path: "/thread/abc?after=1",
      }),
    ];
    const result = normalizeTrajectoryData("t1", steps);
    expect(result!.steps[0].replay_path).toBe("/thread/abc");
    expect(result!.steps[0].result_path).toBe("/thread/abc?after=1");
  });

  it("uses start_path from full payload as step default", () => {
    const payload = makeTrajectoryData({
      start_path: "/settings",
      steps: [makeStep()],
    });
    // Remove step-level replay_path
    delete (payload.steps[0] as Record<string, unknown>).replay_path;
    delete (payload.steps[0] as Record<string, unknown>).result_path;

    const result = normalizeTrajectoryData("t1", payload);
    expect(result!.steps[0].replay_path).toBe("/settings");
    expect(result!.steps[0].result_path).toBe("/settings");
  });
});
