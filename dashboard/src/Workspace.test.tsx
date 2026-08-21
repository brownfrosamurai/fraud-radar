import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { accountChrome } from "./account";
import { Workspace } from "./Workspace";

const scored = {
  id: "11111111-1111-1111-1111-111111111111",
  occurred_at: "2026-01-01T00:00:00Z",
  amount: 20,
  model_score: 0.12,
  decision: "ALLOW",
  model_name: "isolation_forest",
};

const blocked = {
  ...scored,
  id: "b-1",
  amount: 900,
  decision: "BLOCK" as const,
  model_score: 0.95,
};

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: ((ev?: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev?: CloseEvent) => void) | null = null;
  onerror: ((ev?: Event) => void) | null = null;
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

  error() {
    this.onerror?.(new Event("error"));
  }
}

let burstStatus = 200;
let recentRows: typeof scored[] = [];
let recentRowsPromise: Promise<typeof scored[]> | null = null;
let explainStatus = 200;
let explainItems = [
  { feature: "Amount", contribution: 0.42 },
  { feature: "V14", contribution: 0.21 },
];
let explainGate: Promise<void> | null = null;
let lastAlertsUrl = "";
let alertItems: typeof scored[] = [];
let alertTotal = 0;
let alertsGate: Promise<void> | null = null;

beforeEach(() => {
  FakeWebSocket.instances = [];
  burstStatus = 200;
  recentRows = [];
  recentRowsPromise = null;
  explainStatus = 200;
  explainItems = [
    { feature: "Amount", contribution: 0.42 },
    { feature: "V14", contribution: 0.21 },
  ];
  explainGate = null;
  lastAlertsUrl = "";
  alertItems = [];
  alertTotal = 0;
  alertsGate = null;
  vi.stubGlobal("WebSocket", FakeWebSocket);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/score") && init?.method === "POST") {
        throw new Error("POST /score must not be called");
      }
      if (url.includes("/explanation")) {
        if (explainGate) await explainGate;
        return new Response(
          JSON.stringify({
            transaction_id: scored.id,
            explanation: explainItems,
          }),
          { status: explainStatus },
        );
      }
      if (url.includes("/stats")) {
        return new Response(
          JSON.stringify({
            processed: 12,
            throughput_tx_per_s: 1.6,
            latency_p50_ms: 4,
            latency_p95_ms: 9,
            flagged: 3,
          }),
          { status: 200 },
        );
      }
      if (url.includes("/alerts")) {
        lastAlertsUrl = url;
        if (alertsGate) await alertsGate;
        const parsed = new URL(url, "http://local.test");
        const offset = Number(parsed.searchParams.get("offset") || "0");
        const limit = Number(parsed.searchParams.get("limit") || "50");
        const items = alertItems.slice(offset, offset + limit);
        return new Response(
          JSON.stringify({ items, total: alertTotal, offset, limit }),
          { status: 200 },
        );
      }
      if (url.includes("/transactions")) {
        const rows = recentRowsPromise ? await recentRowsPromise : recentRows;
        return new Response(JSON.stringify(rows), { status: 200 });
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
  vi.restoreAllMocks();
});

test("does not POST /score on mount", async () => {
  render(<Workspace />);
  expect(await screen.findByText("Waiting for transactions…")).toBeInTheDocument();
  const fetchMock = vi.mocked(fetch);
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/score"))).toBe(false);
});

test("renders a live row from the websocket", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(scored));
  expect(await screen.findByText("Approved")).toBeInTheDocument();
  expect(screen.getByText(accountChrome(scored.id).line)).toBeInTheDocument();
  expect(within(screen.getByTestId("explain-body")).queryByText("Amount")).not.toBeInTheDocument();
});

test("burst button disables for cooldown_seconds", async () => {
  const user = userEvent.setup();
  render(<Workspace />);
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByRole("button", { name: /cooldown 30s/i })).toBeDisabled();
});

test("burst 503 shows retryable error without cooldown", async () => {
  const user = userEvent.setup();
  burstStatus = 503;
  render(<Workspace />);
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByText(/producer/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /inject synthetic burst/i })).toBeEnabled();
});

test("shows Reconnecting… after socket close", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].close());
  expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
});

test("reconnect hydration keeps the newest 50 across socket and HTTP rows", async () => {
  vi.useFakeTimers();
  const { unmount } = render(<Workspace />);
  await act(async () => {});

  const oldRows = Array.from({ length: 50 }, (_, index) => ({
    ...scored,
    id: `old-${index}`,
    occurred_at: `2026-01-01T00:00:${String(index).padStart(2, "0")}Z`,
    amount: index + 1,
  }));
  act(() => oldRows.forEach((row) => FakeWebSocket.instances[0].emit(row)));

  let resolveRecent!: (rows: typeof scored[]) => void;
  recentRowsPromise = new Promise((resolve) => {
    resolveRecent = resolve;
  });
  act(() => FakeWebSocket.instances[0].close());
  await act(async () => {
    vi.advanceTimersByTime(1000);
  });
  act(() =>
    FakeWebSocket.instances[1].emit({
      ...scored,
      id: "ws-during-hydration",
      occurred_at: "2026-01-03T00:00:00Z",
      amount: 2000,
    }),
  );
  await act(async () => {
    resolveRecent([
      {
        ...scored,
        id: "catch-up-new",
        occurred_at: "2026-01-02T00:00:00Z",
        amount: 1000,
      },
    ]);
  });

  expect(screen.getByText("$2000.00")).toBeInTheDocument();
  expect(screen.getByText("$1000.00")).toBeInTheDocument();
  expect(screen.queryByText("$1.00")).not.toBeInTheDocument();
  expect(screen.getAllByTestId("feed-row")).toHaveLength(50);
  unmount();
  vi.useRealTimers();
});

test("error then delayed close does not create overlapping sockets", async () => {
  vi.useFakeTimers();
  const { unmount } = render(<Workspace />);
  await act(async () => {});
  const first = FakeWebSocket.instances[0];

  act(() => first.error());
  await act(async () => {
    vi.advanceTimersByTime(1000);
  });
  expect(FakeWebSocket.instances).toHaveLength(2);

  act(() => first.close());
  await act(async () => {
    vi.advanceTimersByTime(1000);
  });
  expect(FakeWebSocket.instances).toHaveLength(2);
  unmount();
  vi.useRealTimers();
});

test("explain panel shows mockup chrome and a permutation tooltip", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(blocked));
  expect(await screen.findByRole("button", { name: /what explainability shows/i })).toBeInTheDocument();
  expect(screen.getByRole("tooltip")).toHaveTextContent(/permutation importance/i);
  expect(await screen.findByText(/feature contribution to risk score/i)).toBeInTheDocument();
  expect(screen.getAllByTestId("explain-bar")[0]).toHaveClass("pos");
  expect(screen.getByText("+0.420")).toBeInTheDocument();
});

test("shows explain skeleton while the request is in flight", async () => {
  let release!: () => void;
  explainGate = new Promise((resolve) => {
    release = resolve;
  });
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(blocked));
  expect(await screen.findByTestId("explain-skeleton")).toBeInTheDocument();
  act(() => release());
  expect(await screen.findAllByTestId("explain-bar")).not.toHaveLength(0);
  expect(screen.queryByTestId("explain-skeleton")).not.toBeInTheDocument();
});

test("does not apply a stale explanation to a newer selection", async () => {
  const second = {
    ...blocked,
    id: "22222222-2222-2222-2222-222222222222",
    amount: 800,
  };
  let releaseFirst!: () => void;
  explainGate = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const user = userEvent.setup();
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => {
    FakeWebSocket.instances[0].emit(blocked);
    FakeWebSocket.instances[0].emit(second);
  });
  await screen.findByTestId("explain-skeleton");
  explainItems = [{ feature: "V14", contribution: 0.9 }];
  explainGate = null;
  await user.click(screen.getByRole("button", { name: /\$800\.00/i }));
  act(() => releaseFirst());
  expect(await screen.findByText("V14")).toBeInTheDocument();
  expect(within(screen.getByTestId("explain-body")).queryByText("Amount")).not.toBeInTheDocument();
});

test("501 shows autoencoder isn’t loaded", async () => {
  explainStatus = 501;
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(blocked));
  expect(await screen.findByText("Autoencoder isn’t loaded")).toBeInTheDocument();
});

test("stats rail renders processed and latency", async () => {
  render(<Workspace />);
  expect(await screen.findByTestId("stats-rail")).toBeInTheDocument();
  expect(await screen.findByText("12")).toBeInTheDocument();
  expect(screen.getByText(/4\s*\/\s*9/)).toBeInTheDocument();
});

test("ALLOW feed row is not a button", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit(scored));
  expect(await screen.findByTestId("feed-row")).toBeInTheDocument();
  expect(screen.getByTestId("feed-row")).toHaveClass("feed-row");
  expect(screen.queryByRole("button", { name: /\$20\.00/i })).not.toBeInTheDocument();
});

test("feed scores fill the histogram canvas", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  act(() => FakeWebSocket.instances[0].emit({ ...scored, decision: "BLOCK", model_score: 0.9 }));
  expect(await screen.findByTestId("score-hist")).toBeInTheDocument();
  expect(screen.getByTestId("fraud-rate")).toBeInTheDocument();
});

function makeAlerts(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    ...scored,
    id: `alert-${index}`,
    decision: "REVIEW" as const,
    amount: 100 + index,
    model_score: 0.5,
  }));
}

test("alert header click sorts by amount desc and resets offset", async () => {
  const user = userEvent.setup();
  alertItems = [{ ...scored, decision: "BLOCK", amount: 900, model_score: 0.95 }];
  alertTotal = 1;
  render(<Workspace />);
  await user.click(await screen.findByRole("columnheader", { name: /amount/i }));
  expect(lastAlertsUrl).toMatch(/sort=amount/);
  expect(lastAlertsUrl).toMatch(/dir=desc/);
  expect(lastAlertsUrl).toMatch(/offset=0/);
});

test("next page fetches the following 50 alerts and previous returns", async () => {
  const user = userEvent.setup();
  alertItems = makeAlerts(80);
  alertTotal = 80;
  render(<Workspace />);
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 1–50 of 80");
  expect(screen.getByRole("button", { name: /previous 50 alerts/i })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: /next 50 alerts/i }));
  expect(lastAlertsUrl).toMatch(/offset=50/);
  expect(lastAlertsUrl).toMatch(/limit=50/);
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 51–80 of 80");
  expect(screen.getByText("$150.00")).toBeInTheDocument();
  expect(screen.queryByText("$100.00")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /previous 50 alerts/i }));
  expect(lastAlertsUrl).toMatch(/offset=0/);
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 1–50 of 80");
});

test("alerts footer keeps Next on the right of the shown count", async () => {
  alertItems = makeAlerts(80);
  alertTotal = 80;
  render(<Workspace />);
  const shown = await screen.findByTestId("alerts-shown");
  const next = screen.getByRole("button", { name: /next 50 alerts/i });
  expect(shown.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("clicking an alert row opens explanation", async () => {
  const user = userEvent.setup();
  alertItems = [{ ...scored, id: "alert-1", decision: "BLOCK", amount: 777, model_score: 0.99 }];
  alertTotal = 1;
  render(<Workspace />);
  await user.click(await screen.findByText("$777.00"));
  expect(await screen.findAllByTestId("explain-bar")).not.toHaveLength(0);
});

test("flagged websocket row prepends to alerts without refetching", async () => {
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  await waitFor(() =>
    expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/alerts"))).toBe(
      true,
    ),
  );
  const fetchesBefore = vi
    .mocked(fetch)
    .mock.calls.filter(([input]) => String(input).includes("/alerts")).length;
  act(() => FakeWebSocket.instances[0].emit(blocked));
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 1–1 of 1");
  expect(screen.getAllByText("$900.00").length).toBeGreaterThan(1);
  expect(
    vi.mocked(fetch).mock.calls.filter(([input]) => String(input).includes("/alerts")),
  ).toHaveLength(fetchesBefore);
});

test("alerts table pages 50 at a time instead of capping the whole list", async () => {
  alertItems = makeAlerts(80);
  alertTotal = 80;
  render(<Workspace />);
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 1–50 of 80");
  expect(screen.getByRole("button", { name: /next 50 alerts/i })).toBeEnabled();
  expect(screen.getByRole("button", { name: /previous 50 alerts/i })).toBeDisabled();
  expect(screen.getByText(/50 per page/i)).toBeInTheDocument();
});

test("live alerts stay on page one and only bump the total on later pages", async () => {
  const user = userEvent.setup();
  alertItems = makeAlerts(80);
  alertTotal = 80;
  render(<Workspace />);
  await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
  await user.click(await screen.findByRole("button", { name: /next 50 alerts/i }));
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 51–80 of 80");
  act(() => FakeWebSocket.instances[0].emit(blocked));
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 51–80 of 81");
  expect(within(screen.getByTestId("alerts-table-wrap")).queryByText("$900.00")).not.toBeInTheDocument();
});

test("alerts table shows Source IP from account chrome", async () => {
  alertItems = [{ ...scored, id: "alert-1", decision: "BLOCK", amount: 777, model_score: 0.99 }];
  alertTotal = 1;
  render(<Workspace />);
  expect(await screen.findByRole("columnheader", { name: /source ip/i })).toBeInTheDocument();
  expect(screen.getByText(accountChrome("alert-1").ip)).toBeInTheDocument();
  expect(screen.getByText("Blocked")).toBeInTheDocument();
});

test("shows alerts skeleton while the first request is in flight", async () => {
  let release!: () => void;
  alertsGate = new Promise((resolve) => {
    release = resolve;
  });
  alertItems = [{ ...scored, id: "alert-1", decision: "BLOCK", amount: 777, model_score: 0.99 }];
  alertTotal = 1;
  render(<Workspace />);
  expect(await screen.findByTestId("alerts-skeleton")).toBeInTheDocument();
  act(() => release());
  expect(await screen.findByText("$777.00")).toBeInTheDocument();
  expect(screen.queryByTestId("alerts-skeleton")).not.toBeInTheDocument();
});

test("empty alerts list shows copy, not skeleton, once loaded", async () => {
  render(<Workspace />);
  expect(await screen.findByText("No flagged transactions yet")).toBeInTheDocument();
  expect(screen.queryByTestId("alerts-skeleton")).not.toBeInTheDocument();
});

test("clicking Next does not flash the alerts skeleton", async () => {
  const user = userEvent.setup();
  alertItems = makeAlerts(80);
  alertTotal = 80;
  render(<Workspace />);
  await screen.findByTestId("alerts-shown");

  let release!: () => void;
  alertsGate = new Promise((resolve) => {
    release = resolve;
  });
  await user.click(screen.getByRole("button", { name: /next 50 alerts/i }));
  expect(screen.queryByTestId("alerts-skeleton")).not.toBeInTheDocument();
  expect(screen.getByText("$100.00")).toBeInTheDocument();
  act(() => release());
  expect(await screen.findByTestId("alerts-shown")).toHaveTextContent("Showing 51–80 of 80");
  expect(screen.queryByTestId("alerts-skeleton")).not.toBeInTheDocument();
});
