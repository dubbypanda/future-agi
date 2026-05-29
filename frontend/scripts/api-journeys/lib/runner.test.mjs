import process from "node:process";
import { afterEach, describe, expect, it, vi } from "vitest";
import { runJourneys } from "./runner.mjs";

describe("runJourneys public journey support", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    process.exitCode = undefined;
  });

  it("runs explicitly selected public journeys without authenticated context setup", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const stdoutSpy = vi
      .spyOn(process.stdout, "write")
      .mockImplementation(() => true);
    const result = await runJourneys(
      [
        {
          id: "PUBLIC-TEST",
          title: "Public test",
          public: true,
          async run({ apiBase, client, tokens, user, evidence }) {
            evidence.push({ apiBase, has_client: Boolean(client) });
            expect(tokens).toEqual({});
            expect(user).toBeNull();
          },
        },
      ],
      ["--only", "PUBLIC-TEST"],
    );

    expect(result.status).toBe("passed");
    expect(result.passed).toBe(1);
    expect(result.results[0].evidence[0]).toMatchObject({
      apiBase: "http://localhost:8003",
      has_client: true,
    });
    expect(process.exitCode).toBeUndefined();
    logSpy.mockRestore();
    stdoutSpy.mockRestore();
  });
});
