export type QuotaLimit = {
  kind: "quota-limit";
  provider: "claude-code";
  resetAt: Date | null;
  rawMessage: string;
  resetPhrase: string | null;
};

export type RetryableAgentError = QuotaLimit;

export type QuotaConfig = {
  waitForQuota: boolean;
  quotaBufferMs: number;
  minQuotaWaitMs: number;
  unknownQuotaWaitMs: number;
  maxQuotaRetries?: number;
};

type Clock = () => Date;
type Sleep = (ms: number) => Promise<void>;
type Logger = (message: string) => void;
type OperationLimiter = {
  run<T>(label: string, operation: () => Promise<T>): Promise<T>;
};

const quotaRegex =
  /hit your session limit[\s\S]*?(resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*\(UTC\))/i;

export const readQuotaConfig = (env: Record<string, string | undefined> = process.env): QuotaConfig => ({
  waitForQuota: env.SANDCASTLE_WAIT_FOR_QUOTA !== "0",
  quotaBufferMs: readNonNegativeInteger(env.SANDCASTLE_QUOTA_BUFFER_MS, 120_000, "SANDCASTLE_QUOTA_BUFFER_MS"),
  minQuotaWaitMs: readNonNegativeInteger(env.SANDCASTLE_MIN_QUOTA_WAIT_MS, 60_000, "SANDCASTLE_MIN_QUOTA_WAIT_MS"),
  unknownQuotaWaitMs: readNonNegativeInteger(
    env.SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS,
    900_000,
    "SANDCASTLE_UNKNOWN_QUOTA_WAIT_MS",
  ),
  maxQuotaRetries:
    env.SANDCASTLE_MAX_QUOTA_RETRIES === undefined
      ? undefined
      : readNonNegativeInteger(env.SANDCASTLE_MAX_QUOTA_RETRIES, 0, "SANDCASTLE_MAX_QUOTA_RETRIES"),
});

export const readPositiveInteger = (
  value: string | undefined,
  defaultValue: number,
  name: string,
): number => {
  if (value === undefined || value === "") {
    return defaultValue;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`${name} must be a positive integer.`);
  }
  return parsed;
};

export const parseQuotaLimit = (error: unknown, now = new Date()): RetryableAgentError | null => {
  const rawMessage = stringifyThrownValue(error);
  if (!/hit your session limit/i.test(rawMessage)) {
    return null;
  }

  const match = rawMessage.match(quotaRegex);
  if (!match) {
    return {
      kind: "quota-limit",
      provider: "claude-code",
      resetAt: null,
      rawMessage,
      resetPhrase: null,
    };
  }

  const [, resetPhrase, hourText, minuteText = "00", meridiemText] = match;
  const resetAt = parseResetAtUtc(now, hourText, minuteText, meridiemText);

  return {
    kind: "quota-limit",
    provider: "claude-code",
    resetAt,
    rawMessage,
    resetPhrase,
  };
};

export const computeRetryAt = (
  resetAt: Date | null,
  options: {
    now?: Date;
    bufferMs?: number;
    minWaitMs?: number;
    unknownWaitMs?: number;
  } = {},
): Date => {
  const now = options.now ?? new Date();
  const bufferMs = options.bufferMs ?? 120_000;
  const minWaitMs = options.minWaitMs ?? 60_000;
  const unknownWaitMs = options.unknownWaitMs ?? 900_000;

  if (!resetAt) {
    return new Date(now.getTime() + unknownWaitMs);
  }

  const buffered = new Date(resetAt.getTime() + bufferMs);
  const minimum = new Date(now.getTime() + minWaitMs);
  return buffered.getTime() < minimum.getTime() ? minimum : buffered;
};

export const formatUtc = (date: Date): string => {
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hour}:${minute} UTC`;
};

export const formatDuration = (ms: number): string => {
  const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (minutes > 0 || hours > 0) {
    parts.push(`${minutes}m`);
  }
  parts.push(`${seconds}s`);
  return parts.join(" ");
};

export const formatQuotaExitMessage = (label: string, quota: QuotaLimit): string =>
  [
    `Claude quota reached during ${label}.`,
    `Reset: ${quota.resetAt ? formatUtc(quota.resetAt) : "unknown"}.`,
    "SANDCASTLE_WAIT_FOR_QUOTA=0, so exiting instead of waiting.",
  ].join("\n");

export const formatQuotaRetriesExceededMessage = (
  label: string,
  quota: QuotaLimit,
  retries: number,
): string =>
  [
    `Claude quota reached during ${label}.`,
    `Maximum quota retries reached: ${retries}.`,
    `Last reset: ${quota.resetAt ? formatUtc(quota.resetAt) : "unknown"}.`,
  ].join("\n");

export const formatQuotaWaitMessage = (
  label: string,
  quota: QuotaLimit,
  retryAt: Date,
  waitMs: number,
  attempt: number,
): string =>
  [
    `[${label}] Claude quota reached. Reset: ${quota.resetAt ? formatUtc(quota.resetAt) : "unknown"}.`,
    `[${label}] Waiting ${formatDuration(waitMs)}, then retrying the same operation. Attempt ${attempt}.`,
    `[${label}] Retry time: ${formatUtc(retryAt)}.${quota.resetPhrase ? ` Provider phrase: ${quota.resetPhrase}.` : ""}`,
  ].join("\n");

export class QuotaGate {
  private resumeAt: Date | undefined;
  private waiter: Promise<void> | undefined;
  private paused = false;
  private generation = 0;
  private readonly now: Clock;
  private readonly sleep: Sleep;
  private readonly log: Logger;

  constructor(options: { now?: Clock; sleep?: Sleep; log?: Logger } = {}) {
    this.now = options.now ?? (() => new Date());
    this.sleep = options.sleep ?? sleep;
    this.log = options.log ?? console.log;
  }

  async waitIfPaused(label: string): Promise<void> {
    if (!this.waiter || !this.resumeAt || this.resumeAt.getTime() <= this.now().getTime()) {
      return;
    }

    this.log(`[${label}] Waiting for quota pause to lift at ${formatUtc(this.resumeAt)}.`);
    await this.waiter;
  }

  async pauseUntil(label: string, retryAt: Date, quota: QuotaLimit, attempt: number): Promise<void> {
    const hadActivePause =
      this.waiter !== undefined &&
      this.resumeAt !== undefined &&
      this.resumeAt.getTime() > this.now().getTime();
    const extendsPause = this.resumeAt === undefined || retryAt.getTime() > this.resumeAt.getTime();

    this.paused = true;

    if (extendsPause) {
      this.resumeAt = retryAt;
      this.generation += 1;
    }

    if (!this.waiter || !hadActivePause) {
      this.log(
        `[quota] Claude quota reached by ${label}. Reset: ${quota.resetAt ? formatUtc(quota.resetAt) : "unknown"}.`,
      );
      this.log(`[quota] Pausing all agent calls until ${formatUtc(this.resumeAt ?? retryAt)}. Attempt ${attempt}.`);
      this.waiter = this.waitForResume(this.generation);
    } else if (extendsPause) {
      this.log(`[${label}] Extended existing quota pause until ${formatUtc(retryAt)}.`);
    } else {
      this.log(`[${label}] Joined existing quota pause.`);
    }

    await this.waiter;
  }

  hasPausedForQuota(): boolean {
    return this.paused;
  }

  markPausedForTests(): void {
    this.paused = true;
  }

  private async waitForResume(generation: number): Promise<void> {
    while (this.resumeAt && this.resumeAt.getTime() > this.now().getTime()) {
      await this.sleep(this.resumeAt.getTime() - this.now().getTime());
      if (generation !== this.generation) {
        generation = this.generation;
      }
    }
    this.waiter = undefined;
  }
}

export class DynamicLimiter implements OperationLimiter {
  private active = 0;
  private readonly waiting: Array<() => void> = [];
  private readonly getConcurrency: () => number;

  constructor(getConcurrency: () => number) {
    this.getConcurrency = getConcurrency;
  }

  async run<T>(_label: string, operation: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await operation();
    } finally {
      this.active -= 1;
      this.releaseNext();
    }
  }

  private async acquire(): Promise<void> {
    while (this.active >= Math.max(1, this.getConcurrency())) {
      await new Promise<void>((resolve) => {
        this.waiting.push(resolve);
      });
    }
    this.active += 1;
  }

  private releaseNext(): void {
    const next = this.waiting.shift();
    next?.();
  }
}

export async function runWithQuotaBackoff<T>(
  label: string,
  operation: () => Promise<T>,
  options: {
    workflow: "parallel" | "sequential";
    gate?: QuotaGate;
    config?: Partial<QuotaConfig>;
    now?: Clock;
    sleep?: Sleep;
    log?: Logger;
    afterQuotaLimiter?: OperationLimiter;
  },
): Promise<T> {
  const now = options.now ?? (() => new Date());
  const sleepFn = options.sleep ?? sleep;
  const log = options.log ?? console.log;
  const config = { ...readQuotaConfig(), ...options.config };

  for (let attempt = 1; ; attempt += 1) {
    try {
      await options.gate?.waitIfPaused(label);
      if (options.gate?.hasPausedForQuota() && options.afterQuotaLimiter) {
        return await options.afterQuotaLimiter.run(label, operation);
      }
      return await operation();
    } catch (error) {
      const quota = parseQuotaLimit(error, now());
      if (!quota) {
        throw error;
      }

      if (!config.waitForQuota) {
        throw new Error(formatQuotaExitMessage(label, quota), { cause: error });
      }

      if (config.maxQuotaRetries !== undefined && attempt > config.maxQuotaRetries) {
        throw new Error(formatQuotaRetriesExceededMessage(label, quota, attempt - 1), {
          cause: error,
        });
      }

      const retryAt = computeRetryAt(quota.resetAt, {
        now: now(),
        bufferMs: config.quotaBufferMs,
        minWaitMs: config.minQuotaWaitMs,
        unknownWaitMs: config.unknownQuotaWaitMs,
      });
      const waitMs = Math.max(retryAt.getTime() - now().getTime(), config.minQuotaWaitMs);

      if (options.gate) {
        await options.gate.pauseUntil(label, retryAt, quota, attempt);
        continue;
      }

      log(formatQuotaWaitMessage(`${options.workflow} ${label}`, quota, retryAt, waitMs, attempt));
      await sleepFn(waitMs);
    }
  }
}

export async function runSettledPool<T, R>(
  items: readonly T[],
  worker: (item: T, index: number) => Promise<R>,
  options: { getConcurrency: () => number },
): Promise<PromiseSettledResult<R>[]> {
  const results = new Array<PromiseSettledResult<R>>(items.length);
  const active = new Set<Promise<void>>();
  let nextIndex = 0;

  const startNext = () => {
    const index = nextIndex;
    nextIndex += 1;
    const promise = worker(items[index]!, index)
      .then((value) => {
        results[index] = { status: "fulfilled", value };
      })
      .catch((reason) => {
        results[index] = { status: "rejected", reason };
      })
      .finally(() => {
        active.delete(promise);
      });
    active.add(promise);
  };

  while (nextIndex < items.length || active.size > 0) {
    while (nextIndex < items.length && active.size < Math.max(1, options.getConcurrency())) {
      startNext();
    }

    if (active.size > 0) {
      await Promise.race(active);
    }
  }

  return results;
}

export const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, Math.max(0, ms));
  });

const readNonNegativeInteger = (value: string | undefined, defaultValue: number, name: string): number => {
  if (value === undefined || value === "") {
    return defaultValue;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${name} must be a non-negative integer.`);
  }
  return parsed;
};

const parseResetAtUtc = (
  now: Date,
  hourText: string | undefined,
  minuteText: string,
  meridiemText: string | undefined,
): Date | null => {
  if (!hourText) {
    return null;
  }

  const hour = Number.parseInt(hourText, 10);
  const minute = Number.parseInt(minuteText, 10);
  const meridiem = meridiemText?.toLowerCase();

  if (!Number.isInteger(hour) || !Number.isInteger(minute) || minute > 59) {
    return null;
  }

  let hour24 = hour;
  if (meridiem) {
    if (hour < 1 || hour > 12) {
      return null;
    }
    if (meridiem === "am") {
      hour24 = hour === 12 ? 0 : hour;
    } else {
      hour24 = hour === 12 ? 12 : hour + 12;
    }
  } else if (hour > 23) {
    return null;
  }

  const resetAt = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hour24, minute, 0, 0),
  );
  if (resetAt.getTime() <= now.getTime()) {
    resetAt.setUTCDate(resetAt.getUTCDate() + 1);
  }
  return resetAt;
};

const stringifyThrownValue = (value: unknown): string => {
  const seen = new Set<unknown>();
  const parts: string[] = [];
  let current: unknown = value;

  while (current !== undefined && current !== null && !seen.has(current)) {
    seen.add(current);
    if (current instanceof Error) {
      parts.push(current.message);
      if (current.stack) {
        parts.push(current.stack);
      }
      current = current.cause;
    } else {
      parts.push(String(current));
      break;
    }
  }

  return parts.join("\nCaused by: ");
};
