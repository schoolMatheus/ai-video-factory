import { describe, expect, it } from "vitest";
import { listProductions } from "./client";

describe("client", () => {
  it("carrega produções vazias", async () => {
    const page = await listProductions({});

    expect(page.items).toEqual([]);
    expect(page.next_cursor).toBeNull();
  });
});
