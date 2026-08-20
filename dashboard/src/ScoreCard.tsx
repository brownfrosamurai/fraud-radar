import { useEffect, useRef, useState } from "react";
import {
  fetchExplanation,
  fetchRecent,
  streamUrl,
  triggerBurst,
  type Decision,
  type FeatureContribution,
  type ScoredTransaction,
} from "./api";
import { nextReconnectDelay } from "./reconnect";

const BADGE: Record<Decision, string> = {
  ALLOW: "var(--allow)",
  REVIEW: "var(--review)",
  BLOCK: "var(--block)",
};

function mergeNewest(
  current: ScoredTransaction[],
  incoming: ScoredTransaction[],
): ScoredTransaction[] {
  const byId = new Map<string, ScoredTransaction>();
  for (const row of incoming) byId.set(row.id, row);
  for (const row of current) {
    const other = byId.get(row.id);
    if (!other || Date.parse(row.occurred_at) >= Date.parse(other.occurred_at)) {
      byId.set(row.id, row);
    }
  }
  return [...byId.values()]
    .sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at))
    .slice(0, 50);
}

export function ScoreCard() {
  const [rows, setRows] = useState<ScoredTransaction[]>([]);
  const [selected, setSelected] = useState<ScoredTransaction | null>(null);
  const [explanation, setExplanation] = useState<FeatureContribution[]>([]);
  const [cooldown, setCooldown] = useState(0);
  const [injecting, setInjecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const selectedId = useRef<string | null>(null);

  async function loadExplanation(row: ScoredTransaction) {
    selectedId.current = row.id;
    setSelected(row);
    setExplanation([]);
    setExplaining(true);
    try {
      const result = await fetchExplanation(row.id);
      if (selectedId.current !== row.id) return;
      if (result.status === 200) {
        setExplanation(result.items);
        setError(null);
      } else if (result.status === 501) {
        setExplanation([]);
        setError("Autoencoder isn’t loaded");
      } else {
        setExplanation([]);
        setError("Explanation unavailable");
      }
    } catch {
      if (selectedId.current === row.id) setError("Explanation unavailable");
    } finally {
      if (selectedId.current === row.id) setExplaining(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;
    let generation = 0;

    async function selectTransaction(row: ScoredTransaction) {
      void loadExplanation(row);
    }

    function scheduleReconnect(
      failedSocket: WebSocket,
      failedGeneration: number,
      shouldClose: boolean,
    ) {
      if (
        cancelled ||
        reconnectTimer !== null ||
        socket !== failedSocket ||
        generation !== failedGeneration
      ) {
        return;
      }
      failedSocket.onopen = null;
      failedSocket.onmessage = null;
      failedSocket.onclose = null;
      failedSocket.onerror = null;
      socket = null;
      if (shouldClose) failedSocket.close();
      setReconnecting(true);
      const delay = nextReconnectDelay(attempt);
      attempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        if (!cancelled && generation === failedGeneration && socket === null) connect();
      }, delay);
    }

    function connect() {
      if (cancelled) return;
      const currentGeneration = ++generation;
      const currentSocket = new WebSocket(streamUrl());
      socket = currentSocket;
      currentSocket.onopen = () => {
        if (cancelled || socket !== currentSocket || generation !== currentGeneration) return;
        setReconnecting(false);
        attempt = 0;
        void fetchRecent()
          .then((recent) => {
            if (
              cancelled ||
              socket !== currentSocket ||
              generation !== currentGeneration
            ) {
              return;
            }
            setRows((current) => mergeNewest(current, recent));
            if (!selectedId.current && recent[0]) void selectTransaction(recent[0]);
          })
          .catch(() => {
            if (
              !cancelled &&
              socket === currentSocket &&
              generation === currentGeneration
            ) {
              setError("API unavailable");
            }
          });
      };
      currentSocket.onmessage = (event) => {
        if (cancelled || socket !== currentSocket || generation !== currentGeneration) return;
        const row = JSON.parse(event.data) as ScoredTransaction;
        setRows((current) => mergeNewest(current, [row]));
        if (!selectedId.current) void selectTransaction(row);
      };
      currentSocket.onclose = () =>
        scheduleReconnect(currentSocket, currentGeneration, false);
      currentSocket.onerror = () =>
        scheduleReconnect(currentSocket, currentGeneration, true);
    }

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };
  }, []);

  async function onSelect(row: ScoredTransaction) {
    await loadExplanation(row);
  }

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => window.clearInterval(t);
  }, [cooldown]);

  async function onBurst() {
    setInjecting(true);
    try {
      const { status, body } = await triggerBurst();
      if (status === 200 && body.accepted) {
        setCooldown(body.cooldown_seconds);
        setError(null);
        return;
      }
      if (status === 429) {
        setCooldown(body.cooldown_seconds);
        setError(null);
        return;
      }
      if (status === 503) {
        setError("Producer unavailable");
        return;
      }
      setError("Burst failed");
    } catch {
      setError("Burst failed");
    } finally {
      setInjecting(false);
    }
  }

  const disabled = injecting || cooldown > 0;
  const label = injecting
    ? "Injecting…"
    : cooldown > 0
      ? `Cooldown ${cooldown}s`
      : "Inject Synthetic Burst";

  return (
    <section className="mx-auto mt-16 w-[480px] border border-neutral-700 p-6">
      <p className="text-xs uppercase tracking-wide text-neutral-400">Fraud Radar · Slice 3</p>
      {reconnecting ? <p className="mt-2 text-sm text-neutral-400">Reconnecting…</p> : null}
      {rows.length > 0 ? (
        <ul className="mt-4 space-y-2">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                className="flex w-full justify-between border border-neutral-800 px-3 py-2 text-left font-mono"
                onClick={() => void onSelect(row)}
              >
                <span>${row.amount.toFixed(2)}</span>
                <span className="font-semibold" style={{ color: BADGE[row.decision] }}>
                  {row.decision}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-neutral-400">Waiting for transactions…</p>
      )}
      {selected ? (
        <div className="mt-4">
          <p className="font-mono text-sm text-neutral-400">
            score {selected.model_score.toFixed(2)}
          </p>
          {explaining ? (
            <div className="mt-2 space-y-1" data-testid="explain-skeleton">
              {Array.from({ length: 5 }, (_, index) => (
                <div key={index} className="h-4 animate-pulse bg-neutral-800" />
              ))}
            </div>
          ) : (
            <ul className="mt-2 space-y-1 font-mono text-sm">
              {explanation.map((item) => {
                const max = Math.max(...explanation.map((row) => row.contribution), 1e-9);
                const width = `${Math.round((item.contribution / max) * 100)}%`;
                return (
                  <li key={item.feature}>
                    <div className="flex justify-between">
                      <span>{item.feature}</span>
                      <span>{item.contribution.toFixed(2)}</span>
                    </div>
                    <div className="mt-1 h-1 bg-neutral-800">
                      <div
                        data-testid="explain-bar"
                        className="h-1 bg-cyan-400"
                        style={{ width }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
      {error ? <p className="mt-2 text-sm text-neutral-400">{error}</p> : null}
      <button
        type="button"
        className="mt-6 bg-cyan-400 px-3 py-2 text-sm font-semibold text-black disabled:opacity-50"
        disabled={disabled}
        onClick={onBurst}
      >
        {label}
      </button>
    </section>
  );
}
