import { describe, expect, it } from "vitest";

import { splitAddresses } from "../src/components/ComposeForm";

describe("splitAddresses", () => {
  it("keeps quoted display names with commas intact", () => {
    expect(
      splitAddresses('"Doe, Jane" <JANE@EXAMPLE.COM>, bob@example.com'),
    ).toEqual(["jane@example.com", "bob@example.com"]);
  });

  it("ignores commas inside angle brackets", () => {
    expect(
      splitAddresses("Jane Doe <jane@example.com>, Team <team@example.com>"),
    ).toEqual(["jane@example.com", "team@example.com"]);
  });
});

