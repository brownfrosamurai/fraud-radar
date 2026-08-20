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

export function ScoreCard() {
  const [rows, setRows] = useState<ScoredTransaction[]>([]);
  const [selected, setSelected] = useState<ScoredTransaction | null>(null);
  const [explanation, setExplanation] = useState<FeatureContribution[]>([]);
  const [cooldown, setCooldown] = useState(0);
  const [injecting, setInjecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const selectedId = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;

    async function selectTransaction(row: ScoredTransaction) {
      selectedId.current = row.id;
      setSelected(row);
      try {
        const result = await fetchExplanation(row.id);
        if (!cancelled && selectedId.current === row.id) {
          setExplanation(result);
          setError(null);
        }
      } catch {
        if (!cancelled && selectedId.current === row.id) setError("API unavailable");
      }
    }

    function scheduleReconnect() {
      if (cancelled || reconnectTimer !== null) return;
      setReconnecting(true);
      const delay = nextReconnectDelay(attempt);
      attempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    }

    function connect() {
      if (cancelled) return;
      socket = new WebSocket(streamUrl());
      socket.onopen = () => {
        if (cancelled) return;
        setReconnecting(false);
        attempt = 0;
        void fetchRecent()
          .then((recent) => {
            if (cancelled) return;
            setRows((current) => [
              ...current,
              ...recent.filter((row) => !current.some((item) => item.id === row.id)),
            ].slice(0, 50));
            if (!selectedId.current && recent[0]) void selectTransaction(recent[0]);
          })
          .catch(() => {
            if (!cancelled) setError("API unavailable");
          });
      };
      socket.onmessage = (event) => {
        if (cancelled) return;
        const row = JSON.parse(event.data) as ScoredTransaction;
        setRows((current) => [row, ...current.filter((item) => item.id !== row.id)].slice(0, 50));
        if (!selectedId.current) void selectTransaction(row);
      };
      socket.onclose = scheduleReconnect;
      socket.onerror = scheduleReconnect;
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
    selectedId.current = row.id;
    setSelected(row);
    setExplanation([]);
    try {
      const result = await fetchExplanation(row.id);
      if (selectedId.current === row.id) {
        setExplanation(result);
        setError(null);
      }
    } catch {
      if (selectedId.current === row.id) setError("API unavailable");
    }
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
      <p className="text-xs uppercase tracking-wide text-neutral-400">Fraud Radar · Slice 2</p>
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
          <ul className="mt-2 space-y-1 font-mono text-sm">
            {explanation.map((item) => (
              <li key={item.feature}>
                <span>{item.feature}</span> {item.contribution.toFixed(2)}
              </li>
            ))}
          </ul>
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
