import { describe, expect, it } from "vitest";

import { getThreadNextStarState, isThreadLabelApplied } from "../src/pages/Thread";

describe("getThreadNextStarState", () => {
  it("stars a mixed-state thread instead of un-starring it", () => {
    expect(
      getThreadNextStarState([
        { is_starred: true },
        { is_starred: false },
      ]),
    ).toBe(true);
  });

  it("un-stars only when every message is already starred", () => {
    expect(
      getThreadNextStarState([
        { is_starred: true },
        { is_starred: true },
      ]),
    ).toBe(false);
  });
});

describe("isThreadLabelApplied", () => {
  it("requires the label on every message in the thread", () => {
    expect(
      isThreadLabelApplied(
        [
          { labels: ["Budget Verified"] },
          { labels: [] },
        ],
        "Budget Verified",
      ),
    ).toBe(false);
  });

  it("treats lowercase and display labels as equivalent", () => {
    expect(
      isThreadLabelApplied(
        [
          { labels: ["budget verified"] },
          { labels: ["Budget Verified"] },
        ],
        "Budget Verified",
      ),
    ).toBe(true);
  });
});
