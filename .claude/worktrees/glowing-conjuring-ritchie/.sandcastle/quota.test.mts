import assert from "node:assert/strict";
import { test } from "node:test";
import {
  QuotaGate,
  DynamicLimiter,
  computeRetryAt,
  parseQuotaLimit,
  runSettledPool,
  runWithQuotaBackoff,
} from "./quota.mts";

test("parses Claude quota reset messages", () => {
  const quota = parseQuotaLimit(
    "You've hit your session limit · resets 7:10am (UTC)",
    new Date("2026-06-22T06:00:00Z"),
  );

  assert.equal(quota?.kind, "quota-limit");
  assert.equal(quota?.provider, "claude-code");
  assert.equal(quota?.resetPhrase, "resets 7:10am (UTC)");
  assert.equal(quota?.resetAt?.toISOString(), "2026-06-22T07:10:00.000Z");
});

test("parses uppercase meridiem, 24-hour format, and 12am/12pm", () => {
  assert.equal(
    parseQuotaLimit("hit your session limit resets 7:10PM (UTC)", new Date("2026-06-22T06:00:00Z"))
      ?.resetAt?.toISOString(),
    "2026-06-22T19:10:00.000Z",
  );
  assert.equal(
    parseQuotaLimit("hit your session limit resets 19:10 (UTC)", new Date("2026-06-22T06:00:00Z"))
      ?.resetAt?.toISOString(),
    "2026-06-22T19:10:00.000Z",
  );
  assert.equal(
    parseQuotaLimit("hit your session limit resets 12:00am (UTC)", new Date("2026-06-22T06:00:00Z"))
      ?.resetAt?.toISOString(),
    "2026-06-23T00:00:00.000Z",
  );
  assert.equal(
    parseQuotaLimit("hit your session limit resets 12:00pm (UTC)", new Date("2026-06-22T06:00:00Z"))
      ?.resetAt?.toISOString(),
    "2026-06-22T12:00:00.000Z",
  );
});

test("rejects invalid 24-hour reset times but still classifies quota text", () => {
  const quota = parseQuotaLimit(
    "You've hit your session limit · resets 25:10 (UTC)",
    new Date("2026-06-22T06:00:00Z"),
  );

  assert.equal(quota?.kind, "quota-limit");
  assert.equal(quota?.resetAt, null);
  assert.equal(quota?.resetPhrase, "resets 25:10 (UTC)");
});

test("finds quota text in an error cause chain and ignores ordinary errors", () => {
  const error = new Error("Sandcastle AgentError", {
    cause: new Error("You've hit your session limit · resets 07:10 (UTC)"),
  });

  assert.equal(
    parseQuotaLimit(error, new Date("2026-06-22T06:00:00Z"))?.resetAt?.toISOString(),
    "2026-06-22T07:10:00.000Z",
  );
  assert.equal(parseQuotaLimit(new Error("ordinary task failure")), null);
});

test("computes retry times with buffer, tomorrow rollover, minimum, and unknown fallback", () => {
  assert.equal(
    computeRetryAt(new Date("2026-06-22T07:10:00Z"), {
      now: new Date("2026-06-22T06:30:00Z"),
      bufferMs: 120_000,
      minWaitMs: 60_000,
      unknownWaitMs: 900_000,
    }).toISOString(),
    "2026-06-22T07:12:00.000Z",
  );
  assert.equal(
    parseQuotaLimit(
      "You've hit your session limit · resets 7:10am (UTC)",
      new Date("2026-06-22T08:00:00Z"),
    )?.resetAt?.toISOString(),
    "2026-06-23T07:10:00.000Z",
  );
  assert.equal(
    computeRetryAt(new Date("2026-06-22T06:30:10Z"), {
      now: new Date("2026-06-22T06:30:00Z"),
      bufferMs: 0,
      minWaitMs: 60_000,
      unknownWaitMs: 900_000,
    }).toISOString(),
    "2026-06-22T06:31:00.000Z",
  );
  assert.equal(
    computeRetryAt(null, {
      now: new Date("2026-06-22T06:30:00Z"),
      bufferMs: 120_000,
      minWaitMs: 60_000,
      unknownWaitMs: 900_000,
    }).toISOString(),
    "2026-06-22T06:45:00.000Z",
  );
});

test("runWithQuotaBackoff honors fail-fast and max retries", async () => {
  await assert.rejects(
    runWithQuotaBackoff(
      "implementer issue 5",
      async () => {
        throw new Error("You've hit your session limit · resets 7:10am (UTC)");
      },
      {
        workflow: "parallel",
        config: { waitForQuota: false },
        now: () => new Date("2026-06-22T06:00:00Z"),
      },
    ),
    /SANDCASTLE_WAIT_FOR_QUOTA=0/,
  );

  let attempts = 0;
  await assert.rejects(
    runWithQuotaBackoff(
      "reviewer issue 3",
      async () => {
        attempts += 1;
        throw new Error("You've hit your session limit · resets 7:10am (UTC)");
      },
      {
        workflow: "parallel",
        config: { maxQuotaRetries: 1, minQuotaWaitMs: 0, quotaBufferMs: 0 },
        now: () => new Date("2026-06-22T06:00:00Z"),
        sleep: async () => {},
        log: () => {},
      },
    ),
    /Maximum quota retries reached: 1/,
  );
  assert.equal(attempts, 2);
});

test("QuotaGate coordinates simultaneous quota errors and extends later pauses", async () => {
  const waits: number[] = [];
  const resolvers: Array<() => void> = [];
  const logs: string[] = [];
  let currentTime = new Date("2026-06-22T06:00:00Z");
  const gate = new QuotaGate({
    now: () => currentTime,
    sleep: async (ms) => {
      waits.push(ms);
      await new Promise<void>((resolve) => {
        resolvers.push(resolve);
      });
    },
    log: (message) => logs.push(message),
  });
  const quota = parseQuotaLimit(
    "You've hit your session limit · resets 7:10am (UTC)",
    new Date("2026-06-22T06:00:00Z"),
  )!;

  const first = gate.pauseUntil("implementer issue 3", new Date("2026-06-22T07:12:00Z"), quota, 1);
  const second = gate.pauseUntil("implementer issue 5", new Date("2026-06-22T07:12:00Z"), quota, 1);
  const third = gate.pauseUntil("implementer issue 9", new Date("2026-06-22T07:20:00Z"), quota, 1);

  assert.equal(waits.length, 1);
  currentTime = new Date("2026-06-22T07:12:00Z");
  resolvers.shift()?.();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(waits.length, 2);

  currentTime = new Date("2026-06-22T07:20:00Z");
  resolvers.shift()?.();
  await Promise.all([first, second, third]);

  assert.deepEqual(waits, [4_320_000, 480_000]);
  assert.equal(logs.filter((line) => line.includes("Pausing all agent calls")).length, 1);
  assert.ok(logs.some((line) => line.includes("Joined existing quota pause")));
  assert.ok(logs.some((line) => line.includes("Extended existing quota pause")));
  assert.equal(gate.hasPausedForQuota(), true);
});

test("runSettledPool keeps results aligned and reduces starts after quota pause", async () => {
  const gate = new QuotaGate({
    now: () => new Date("2026-06-22T06:00:00Z"),
    sleep: async () => {},
    log: () => {},
  });
  const started: number[] = [];

  const settled = await runSettledPool([1, 2, 3, 4], async (value) => {
    started.push(value);
    if (value === 1) {
      gate.markPausedForTests();
    }
    if (value === 3) {
      throw new Error("boom");
    }
    return value * 10;
  }, {
    getConcurrency: () => (gate.hasPausedForQuota() ? 1 : 2),
  });

  assert.deepEqual(started, [1, 2, 3, 4]);
  assert.deepEqual(
    settled.map((entry) => entry.status === "fulfilled" ? entry.value : "rejected"),
    [10, 20, "rejected", 40],
  );
});

test("runWithQuotaBackoff limits simultaneous operations after a quota pause", async () => {
  const gate = new QuotaGate({ sleep: async () => {}, log: () => {} });
  gate.markPausedForTests();
  const limiter = new DynamicLimiter(() => 1);
  let active = 0;
  let maxActive = 0;

  await Promise.all([
    runWithQuotaBackoff("implementer issue 1", async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setImmediate(resolve));
      active -= 1;
      return "one";
    }, { workflow: "parallel", gate, afterQuotaLimiter: limiter }),
    runWithQuotaBackoff("implementer issue 2", async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setImmediate(resolve));
      active -= 1;
      return "two";
    }, { workflow: "parallel", gate, afterQuotaLimiter: limiter }),
  ]);

  assert.equal(maxActive, 1);
});
