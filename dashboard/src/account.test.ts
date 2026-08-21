import { expect, test } from "vitest";
import { ACCOUNT_IPS, ACCOUNT_METHODS, accountChrome } from "./account";

test("accountChrome is stable for an id and uses mockup IP and method lists", () => {
  const first = accountChrome("11111111-1111-1111-1111-111111111111");
  const second = accountChrome("11111111-1111-1111-1111-111111111111");
  expect(first).toEqual(second);
  expect(first.line).toBe(`${first.ip} · ${first.method}`);
  expect(ACCOUNT_IPS).toContain(first.ip);
  expect(ACCOUNT_METHODS).toContain(first.method);
});

test("different ids can map to different account chrome", () => {
  const lines = new Set(Array.from({ length: 40 }, (_, i) => accountChrome(`id-${i}`).line));
  expect(lines.size).toBeGreaterThan(1);
});
