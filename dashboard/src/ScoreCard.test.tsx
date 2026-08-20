import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScoreCard } from "./ScoreCard";

const scored = {
  id: "11111111-1111-1111-1111-111111111111",
  occurred_at: "2026-01-01T00:00:00Z",
  amount: 20,
  model_score: 0.12,
  decision: "ALLOW",
  model_name: "isolation_forest",
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/score") && init?.method === "POST") {
        return new Response(JSON.stringify(scored), { status: 200 });
      }
      if (url.includes("/explanation")) {
        return new Response(
          JSON.stringify({
            transaction_id: scored.id,
            explanation: [
              { feature: "Amount", contribution: 0.42 },
              { feature: "V14", contribution: 0.21 },
            ],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/transactions")) {
        return new Response(JSON.stringify([scored]), { status: 200 });
      }
      if (url.endsWith("/demo/burst") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            accepted: true,
            size: 50,
            window_ms: 2000,
            cooldown_seconds: 30,
          }),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders decision and canned explanation feature names", async () => {
  render(<ScoreCard />);
  expect(await screen.findByText("ALLOW")).toBeInTheDocument();
  expect(await screen.findByText("Amount")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /inject synthetic burst/i })).toBeEnabled();
});

test("burst button disables for cooldown_seconds", async () => {
  const user = userEvent.setup();
  render(<ScoreCard />);
  await screen.findByText("ALLOW");
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByRole("button", { name: /cooldown 30s/i })).toBeDisabled();
});
