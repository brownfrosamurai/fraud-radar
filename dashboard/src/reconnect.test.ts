import { expect, test } from "vitest";
import { nextReconnectDelay } from "./reconnect";

test("backoff is 1s 2s 4s then cap 8s", () => {
  expect(nextReconnectDelay(0)).toBe(1000);
  expect(nextReconnectDelay(1)).toBe(2000);
  expect(nextReconnectDelay(2)).toBe(4000);
  expect(nextReconnectDelay(3)).toBe(8000);
  expect(nextReconnectDelay(9)).toBe(8000);
});
