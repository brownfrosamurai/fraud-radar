import { act, render, screen, waitFor } from "@testing-library/react";
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

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: ((ev?: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev?: CloseEvent) => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.(new Event("open")));
  }

  close() {
    this.onclose?.(new CloseEvent("close"));
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

let burstStatus = 200;

beforeEach(() => {
  FakeWebSocket.instances = [];
  burstStatus = 200;
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/score") && init?.method === "POST") {
        throw new Error("POST /score must not be called");
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
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.endsWith("/demo/burst") && init?.method === "POST") {
        if (burstStatus === 503) {
          return new Response(
            JSON.stringify({
              accepted: false,
              size: 0,
              window_ms: 2000,
              cooldown_seconds: 0,
            }),
            { status: 503 },
          );
        }
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

test("does not POST /score on mount", async () => {
  render(<ScoreCard />);
  expect(await screen.findByText("Waiting for transactions…")).toBeInTheDocument();
  const fetchMock = vi.mocked(fetch);
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/score"))).toBe(false);
});

test("renders a live row from the websocket", async () => {
  render(<ScoreCard />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(scored));
  expect(await screen.findByText("ALLOW")).toBeInTheDocument();
  expect(await screen.findByText("Amount")).toBeInTheDocument();
});

test("burst button disables for cooldown_seconds", async () => {
  const user = userEvent.setup();
  render(<ScoreCard />);
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByRole("button", { name: /cooldown 30s/i })).toBeDisabled();
});

test("burst 503 shows retryable error without cooldown", async () => {
  const user = userEvent.setup();
  burstStatus = 503;
  render(<ScoreCard />);
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByText(/producer/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /inject synthetic burst/i })).toBeEnabled();
});

test("shows Reconnecting… after socket close", async () => {
  render(<ScoreCard />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].close());
  expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
});
