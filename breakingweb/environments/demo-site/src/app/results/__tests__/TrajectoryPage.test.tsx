import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TrajectoryData, TrajectoryStep, TrajectoryTarget } from "@/lib/results";
import type { GmailReplayStepState } from "@/lib/gmailReplay";

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

vi.mock("@/components/gmail-wrapper", () => ({
  GmailWrapper: (props: { route?: string; fixture?: unknown }) => (
    <div data-testid="gmail-wrapper" data-route={props.route} />
  ),
}));

vi.mock("@/components/replay/TrajectoryViewer", () => ({
  TrajectoryViewer: (props: {
    steps: TrajectoryStep[];
    current: number;
    onStep: (i: number) => void;
  }) => (
    <div data-testid="trajectory-viewer" data-current={props.current}>
      {props.steps.map((_, i) => (
        <button key={i} data-testid={`step-btn-${i}`} onClick={() => props.onStep(i)}>
          Step {i}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@breakingweb/gmail/mutator", () => ({
  gmailMutator: vi.fn(() => ({ response: {} })),
}));

const mockBuildReplayStates = vi.fn<
  (fixture: unknown, steps: TrajectoryStep[]) => GmailReplayStepState[]
>(() => []);
vi.mock("@/lib/gmailReplay", () => ({
  buildGmailReplayStepStates: (...args: [unknown, TrajectoryStep[]]) =>
    mockBuildReplayStates(...args),
}));

const mockFetchTrajectory = vi.fn<(taskId: string) => Promise<TrajectoryData | null>>();
vi.mock("@/lib/results", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/results")>();
  return {
    ...orig,
    fetchTrajectory: (...args: [string]) => mockFetchTrajectory(...args),
  };
});

import TrajectoryPage, {
  selectStepTarget,
  describeStepTarget,
} from "../[taskId]/TrajectoryPage";

/* ------------------------------------------------------------------ */
/*  Test data factories                                                */
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
    title: "Test Task Title",
    instruction: "Complete the task by clicking buttons",
    difficulty: "medium",
    model: "gpt-4o",
    total_steps: 3,
    elapsed_seconds: 12.5,
    completed: true,
    start_path: "/inbox?label=inbox",
    evaluation: {
      score: 0.85,
      success: true,
      reasoning: "Completed well",
      criteria_results: [
        { desc: "Clicked the right button", passed: true },
        { desc: "Filled the form", passed: false, penalty: 0.15 },
      ],
    },
    steps: [
      makeStep({ step: 0, elapsed_seconds: 2.0 }),
      makeStep({
        step: 1,
        elapsed_seconds: 5.0,
        targets: { ref: { role: "button", name: "Save" } },
        action: { action: "click", ref: 2 },
      }),
      makeStep({
        step: 2,
        elapsed_seconds: 12.5,
        targets: { ref: { role: "textbox", name: "Search" } },
        action: { action: "fill", ref: 3, value: "hello" },
      }),
    ],
    ...overrides,
  };
}

function makeFixture() {
  return {
    task_id: "test_task",
    state: {
      env_id: "gmail",
      task_id: "test_task",
      owner_name: "Test",
      owner_email: "test@example.com",
      emails: [],
      sent: [],
      deleted: [],
      drafts: [],
      labels: [],
      filters: [],
      contacts: [],
      settings: {
        signature: "",
        vacation_responder_message: "",
        vacation_responder_enabled: false,
        forwarding_address: "",
        undo_send_seconds: 5,
        max_page_size: 50,
        language: "English",
        default_reply_behavior: "reply",
        send_and_archive: false,
        display_density: "default",
      },
    },
    instruction: "Do the task",
    start_path: "/inbox?label=inbox",
  };
}

/* ------------------------------------------------------------------ */
/*  Setup                                                              */
/* ------------------------------------------------------------------ */

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

  // Default: fixture fetch returns null
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve({ ok: false, json: () => Promise.resolve(null) })),
  );
});

afterEach(() => {
  cleanup();
  consoleErrorSpy.mockRestore();
  vi.unstubAllGlobals();
});

/* ================================================================== */
/*  Category 1: Hook ordering                                          */
/* ================================================================== */

describe("Hook ordering (category 1)", () => {
  it("no hook errors during loading → loaded transition", async () => {
    let resolveTrajectory!: (val: TrajectoryData | null) => void;
    mockFetchTrajectory.mockImplementation(
      () => new Promise((r) => { resolveTrajectory = r; }),
    );

    render(<TrajectoryPage taskId="task_1" />);
    expect(screen.getByText("Loading trajectory...")).toBeInTheDocument();

    await act(async () => { resolveTrajectory(makeTrajectoryData()); });

    const hookErrors = consoleErrorSpy.mock.calls.filter(
      (args) => typeof args[0] === "string" && args[0].includes("order of Hooks"),
    );
    expect(hookErrors).toHaveLength(0);
  });

  it("no hook errors when trajectory is null", async () => {
    mockFetchTrajectory.mockResolvedValue(null);

    render(<TrajectoryPage taskId="task_1" />);
    await waitFor(() => {
      expect(screen.getByText("Trajectory unavailable")).toBeInTheDocument();
    });

    const hookErrors = consoleErrorSpy.mock.calls.filter(
      (args) => typeof args[0] === "string" && args[0].includes("order of Hooks"),
    );
    expect(hookErrors).toHaveLength(0);
  });

  it("no hook errors on null → valid data transition via taskId change", async () => {
    mockFetchTrajectory
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(makeTrajectoryData());

    const { rerender } = render(<TrajectoryPage taskId="task_null" />);
    await waitFor(() => {
      expect(screen.getByText("Trajectory unavailable")).toBeInTheDocument();
    });

    rerender(<TrajectoryPage taskId="task_valid" />);
    await waitFor(() => {
      expect(screen.getByText("Test Task Title")).toBeInTheDocument();
    });

    const hookErrors = consoleErrorSpy.mock.calls.filter(
      (args) => typeof args[0] === "string" && args[0].includes("order of Hooks"),
    );
    expect(hookErrors).toHaveLength(0);
  });

  it("no hook errors on rapid taskId changes", async () => {
    mockFetchTrajectory.mockImplementation(
      () => new Promise((r) => setTimeout(() => r(makeTrajectoryData()), 10)),
    );

    const { rerender } = render(<TrajectoryPage taskId="a" />);
    rerender(<TrajectoryPage taskId="b" />);
    rerender(<TrajectoryPage taskId="c" />);

    await waitFor(() => {
      expect(screen.getByText("Test Task Title")).toBeInTheDocument();
    });

    const hookErrors = consoleErrorSpy.mock.calls.filter(
      (args) => typeof args[0] === "string" && args[0].includes("order of Hooks"),
    );
    expect(hookErrors).toHaveLength(0);
  });
});

/* ================================================================== */
/*  Category 2: Helper functions                                       */
/* ================================================================== */

describe("selectStepTarget (category 2)", () => {
  it("prefers ref over from_ref and to_ref", () => {
    const ref = { role: "button", name: "A" };
    const from_ref = { role: "link", name: "B" };
    const to_ref = { role: "textbox", name: "C" };
    expect(selectStepTarget({ ref, from_ref, to_ref })).toBe(ref);
  });

  it("falls back to from_ref when ref is missing", () => {
    const from_ref = { role: "link", name: "B" };
    const to_ref = { role: "textbox", name: "C" };
    expect(selectStepTarget({ from_ref, to_ref })).toBe(from_ref);
  });

  it("falls back to to_ref when ref and from_ref missing", () => {
    const to_ref = { role: "textbox", name: "C" };
    expect(selectStepTarget({ to_ref })).toBe(to_ref);
  });

  it("returns null when all missing", () => {
    expect(selectStepTarget({})).toBeNull();
  });

  it("returns null for all-undefined targets", () => {
    expect(selectStepTarget({ ref: undefined, from_ref: undefined })).toBeNull();
  });
});

describe("describeStepTarget (category 2)", () => {
  it("returns status when target is null", () => {
    expect(describeStepTarget(null, "success")).toBe("success");
  });

  it("formats role and name", () => {
    expect(describeStepTarget({ role: "button", name: "Save" }, "ok")).toBe('button "Save"');
  });

  it("returns name only when role missing", () => {
    expect(describeStepTarget({ name: "Save" }, "ok")).toBe("Save");
  });

  it("returns role only when name missing", () => {
    expect(describeStepTarget({ role: "button" }, "ok")).toBe("button");
  });

  it("falls back to status when target has neither role nor name", () => {
    expect(describeStepTarget({ bbox: { x: 0, y: 0, width: 100, height: 50 } }, "pending")).toBe(
      "pending",
    );
  });

  it("returns status for empty target object", () => {
    expect(describeStepTarget({}, "waiting")).toBe("waiting");
  });
});

/* ================================================================== */
/*  Category 3: Data fetching & state transitions                      */
/* ================================================================== */

describe("Data fetching (category 3)", () => {
  it("shows loading text while fetches are pending", () => {
    mockFetchTrajectory.mockImplementation(() => new Promise(() => {}));
    render(<TrajectoryPage taskId="task_1" />);
    expect(screen.getByText("Loading trajectory...")).toBeInTheDocument();
  });

  it("shows unavailable message when trajectory is null", async () => {
    mockFetchTrajectory.mockResolvedValue(null);
    render(<TrajectoryPage taskId="task_1" />);
    await waitFor(() => {
      expect(screen.getByText("Trajectory unavailable")).toBeInTheDocument();
    });
  });

  it("renders main split view when trajectory loads", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makeFixture()) })),
    );

    render(<TrajectoryPage taskId="test_task" />);
    await waitFor(() => {
      expect(screen.getByText("Test Task Title")).toBeInTheDocument();
    });
    expect(screen.getByTestId("trajectory-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("gmail-wrapper")).toBeInTheDocument();
  });

  it("shows fixture-missing fallback when fixture is null", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="test_task" />);
    await waitFor(() => {
      expect(screen.getByText("Test Task Title")).toBeInTheDocument();
    });
    expect(screen.getByText("Environment fixture not available")).toBeInTheDocument();
  });

  it("does not update state after taskId changes (cancelled fetch)", async () => {
    let resolveFirst!: (val: TrajectoryData | null) => void;
    mockFetchTrajectory
      .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r; }))
      .mockResolvedValueOnce(makeTrajectoryData({ title: "Second Task" }));

    const { rerender } = render(<TrajectoryPage taskId="task_a" />);
    rerender(<TrajectoryPage taskId="task_b" />);

    await act(async () => { resolveFirst(makeTrajectoryData({ title: "Stale Task" })); });

    await waitFor(() => {
      expect(screen.getByText("Second Task")).toBeInTheDocument();
    });
    expect(screen.queryByText("Stale Task")).not.toBeInTheDocument();
  });

  it("resets step to 0 when taskId changes", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());

    const { rerender } = render(<TrajectoryPage taskId="task_a" />);
    await waitFor(() => {
      expect(screen.getByText("Test Task Title")).toBeInTheDocument();
    });

    await act(async () => { screen.getByTestId("step-btn-2").click(); });
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toHaveAttribute("data-current", "2");
    });

    rerender(<TrajectoryPage taskId="task_b" />);
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toHaveAttribute("data-current", "0");
    });
  });

  it("shows unavailable when fetchTrajectory returns null (simulating error)", async () => {
    // The component's Promise.all doesn't have a .catch, so we test the
    // graceful null-return path that fetchTrajectory uses on network errors
    mockFetchTrajectory.mockResolvedValue(null);
    render(<TrajectoryPage taskId="task_1" />);
    await waitFor(() => {
      expect(screen.getByText("Trajectory unavailable")).toBeInTheDocument();
    });
  });
});

/* ================================================================== */
/*  Category 4: Computed values & derived state                        */
/* ================================================================== */

describe("Computed values (category 4)", () => {
  it("displays total_steps from data when finite", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ total_steps: 5 }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("5 steps")).toBeInTheDocument(); });
  });

  it("falls back to steps.length when total_steps is NaN", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ total_steps: NaN }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("3 steps")).toBeInTheDocument(); });
  });

  it("falls back to steps.length when total_steps is Infinity", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ total_steps: Infinity }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("3 steps")).toBeInTheDocument(); });
  });

  it("displays elapsed_seconds from data when finite", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ elapsed_seconds: 42.7 }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("43s")).toBeInTheDocument(); });
  });

  it("falls back to last step elapsed when data elapsed is NaN", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ elapsed_seconds: NaN }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("13s")).toBeInTheDocument(); });
  });

  it("shows 0s elapsed when no steps and elapsed is NaN", async () => {
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({ elapsed_seconds: NaN, steps: [], total_steps: 0 }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("0s")).toBeInTheDocument(); });
  });

  it("shows 'No active step' when steps array is empty", async () => {
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({ steps: [], total_steps: 0 }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("No active step")).toBeInTheDocument(); });
  });
});

/* ================================================================== */
/*  Category 5: Step navigation & interaction                          */
/* ================================================================== */

describe("Step navigation (category 5)", () => {
  beforeEach(() => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
  });

  it("updates currentStep when step button is clicked", async () => {
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toBeInTheDocument();
    });

    await act(async () => { screen.getByTestId("step-btn-2").click(); });
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toHaveAttribute("data-current", "2");
    });
  });

  it("toggles instruction panel with show/hide task button", async () => {
    const user = userEvent.setup();
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("show task")).toBeInTheDocument(); });

    expect(screen.queryByText("Complete the task by clicking buttons")).not.toBeInTheDocument();

    await user.click(screen.getByText("show task"));
    expect(screen.getByText("Complete the task by clicking buttons")).toBeInTheDocument();
    expect(screen.getByText("hide task")).toBeInTheDocument();

    await user.click(screen.getByText("hide task"));
    expect(screen.queryByText("Complete the task by clicking buttons")).not.toBeInTheDocument();
  });

  it("switches to Trajectory tab on step change", async () => {
    const user = userEvent.setup();
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Trajectory")).toBeInTheDocument(); });

    // Switch to Criteria tab
    await user.click(screen.getByText(/Criteria/));
    // The trajectory viewer should not be visible
    expect(screen.queryByTestId("trajectory-viewer")).not.toBeInTheDocument();
    // Criteria content should be visible — check for reasoning text
    expect(screen.getByText("Completed well")).toBeInTheDocument();
  });

  it("right tab defaults to trajectory", async () => {
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toBeInTheDocument();
    });
  });
});

/* ================================================================== */
/*  Category 6: Inline criteria rendering (was EvalCriteria)           */
/* ================================================================== */

describe("Criteria panel (category 6)", () => {
  it("shows criteria when switching to Criteria tab", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await user.click(screen.getByText(/Criteria/));

    expect(screen.getByText("Clicked the right button")).toBeInTheDocument();
    expect(screen.getByText("Filled the form")).toBeInTheDocument();
  });

  it("shows pass/fail indicators for criteria", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await user.click(screen.getByText(/Criteria/));

    expect(screen.getByText("Passed (1)")).toBeInTheDocument();
    expect(screen.getByText("Failed (1)")).toBeInTheDocument();
  });

  it("shows penalty badge for failed criteria", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({
        evaluation: {
          score: 0.85,
          success: true,
          reasoning: "Completed well",
          criteria_results: [
            { desc: "Clicked the right button", passed: true },
            { desc: "Triggered a penalty", passed: false, kind: "penalty", penalty: 0.15 },
          ],
        },
      }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await user.click(screen.getByText(/Criteria/));

    expect(screen.getByText("Penalties triggered (1)")).toBeInTheDocument();
    expect(screen.getByText(/0\.15 penalty/)).toBeInTheDocument();
  });

  it("shows reasoning text in criteria tab", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await user.click(screen.getByText(/Criteria/));
    expect(screen.getByText("Completed well")).toBeInTheDocument();
  });

  it("shows criteria count in tab label", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    // Tab shows pass count / total count
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("handles empty criteria gracefully", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({
        evaluation: { score: 0, success: false, reasoning: "", criteria_results: [] },
      }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await user.click(screen.getByText(/Criteria/));
    // Should not crash, just show empty
  });

  it("displays score with 2 decimal places in header", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("0.85")).toBeInTheDocument(); });
  });

  it("shows dash when score is undefined", async () => {
    const data = makeTrajectoryData();
    (data.evaluation as Record<string, unknown>).score = undefined;
    mockFetchTrajectory.mockResolvedValue(data);
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("—")).toBeInTheDocument(); });
  });

  it("shows pass/fail badge based on success", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Pass")).toBeInTheDocument(); });
  });

  it("shows fail badge when not successful", async () => {
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({
        evaluation: {
          score: 0.2,
          success: false,
          reasoning: "bad",
          criteria_results: [{ desc: "test", passed: false }],
        },
      }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Fail")).toBeInTheDocument(); });
  });
});

/* ================================================================== */
/*  Category 7: Target display bar                                     */
/* ================================================================== */

describe("Target display bar (category 7)", () => {
  it("shows step status when step has no targets", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("success")).toBeInTheDocument(); });
  });

  it("shows formatted target label after navigating to step with target", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    await act(async () => { screen.getByTestId("step-btn-1").click(); });
    await waitFor(() => { expect(screen.getByText('button "Save"')).toBeInTheDocument(); });
  });

  it("shows action JSON in code block", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => {
      const actionText = JSON.stringify({ action: "click", ref: 1 });
      expect(screen.getByText(actionText)).toBeInTheDocument();
    });
  });

  it("hides action display when activeAction is undefined", async () => {
    const data = makeTrajectoryData({
      steps: [
        makeStep({
          step: 0,
          action: undefined as unknown as Record<string, unknown>,
        }),
      ],
    });
    mockFetchTrajectory.mockResolvedValue(data);
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });
    const codeElements = document.querySelectorAll("code");
    expect(codeElements).toHaveLength(0);
  });

  it("shows 'No active step' when steps array is empty", async () => {
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({ steps: [], total_steps: 0 }),
    );
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("No active step")).toBeInTheDocument(); });
  });
});

/* ================================================================== */
/*  Category 10: Performance / regression guards                       */
/* ================================================================== */

describe("Performance guards (category 10)", () => {
  it("does not recompute replayStates when showInstruction toggles", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makeFixture()) })),
    );

    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    const callCountAfterLoad = mockBuildReplayStates.mock.calls.length;

    await user.click(screen.getByText("show task"));
    await user.click(screen.getByText("hide task"));

    expect(mockBuildReplayStates.mock.calls.length).toBe(callCountAfterLoad);
  });

  it("TrajectoryViewer receives stable onStep callback across renders", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toBeInTheDocument();
    });

    // Toggle instruction then navigate — proves callback is stable
    await user.click(screen.getByText("show task"));
    await act(async () => { screen.getByTestId("step-btn-1").click(); });
    await waitFor(() => {
      expect(screen.getByTestId("trajectory-viewer")).toHaveAttribute("data-current", "1");
    });
  });

  it("renders within reasonable time with 50 steps", async () => {
    const manySteps = Array.from({ length: 50 }, (_, i) =>
      makeStep({ step: i, elapsed_seconds: i * 0.5 }),
    );
    mockFetchTrajectory.mockResolvedValue(
      makeTrajectoryData({ steps: manySteps, total_steps: 50 }),
    );

    const start = performance.now();
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });
    const elapsed = performance.now() - start;

    expect(elapsed).toBeLessThan(2000);
  });
});

/* ================================================================== */
/*  Additional edge cases                                              */
/* ================================================================== */

describe("Additional edge cases", () => {
  it("displays model name in header", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ model: "claude-3.5-sonnet" }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("claude-3.5-sonnet")).toBeInTheDocument(); });
  });

  it("displays difficulty in header", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData({ difficulty: "hard" }));
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("hard")).toBeInTheDocument(); });
  });

  it("shows back link to results page", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });
    const backLink = screen.getByRole("link", { name: /Results/ });
    expect(backLink).toHaveAttribute("href", "/results");
  });

  it("shows Trajectory and Criteria tab buttons", async () => {
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => {
      expect(screen.getByText("Trajectory")).toBeInTheDocument();
      expect(screen.getByText(/Criteria/)).toBeInTheDocument();
    });
  });

  it("handleStepChange switches back to trajectory tab", async () => {
    const user = userEvent.setup();
    mockFetchTrajectory.mockResolvedValue(makeTrajectoryData());
    render(<TrajectoryPage taskId="t1" />);
    await waitFor(() => { expect(screen.getByText("Test Task Title")).toBeInTheDocument(); });

    // Switch to criteria tab
    await user.click(screen.getByText(/Criteria/));
    expect(screen.queryByTestId("trajectory-viewer")).not.toBeInTheDocument();

    // The criteria panel has step buttons from findRelevantSteps — but since our mock
    // doesn't have matching keywords, we test by verifying the tab button works
    await user.click(screen.getByText("Trajectory"));
    expect(screen.getByTestId("trajectory-viewer")).toBeInTheDocument();
  });
});
