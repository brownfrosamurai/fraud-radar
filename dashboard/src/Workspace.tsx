import { useEffect, useRef, useState } from "react";
import {
  fetchExplanation,
  fetchRecent,
  fetchStats,
  streamUrl,
  triggerBurst,
  type Decision,
  type FeatureContribution,
  type ScoredTransaction,
  type Stats,
} from "./api";
import { nextReconnectDelay } from "./reconnect";

const BADGE: Record<Decision, string> = {
  ALLOW: "allow",
  REVIEW: "review",
  BLOCK: "block",
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

function formatLatency(stats: Stats | null): string {
  if (!stats || stats.latency_p50_ms === null || stats.latency_p95_ms === null) return "—";
  return `${stats.latency_p50_ms} / ${stats.latency_p95_ms}`;
}

function formatTime(iso: string): string {
  return new Date(iso).toISOString().slice(11, 19);
}

export function Workspace() {
  const [rows, setRows] = useState<ScoredTransaction[]>([]);
  const [selected, setSelected] = useState<ScoredTransaction | null>(null);
  const [explanation, setExplanation] = useState<FeatureContribution[]>([]);
  const [cooldown, setCooldown] = useState(0);
  const [injecting, setInjecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
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

    async function poll() {
      try {
        const result = await fetchStats();
        if (cancelled) return;
        if (result.status === 200 && result.body) setStats(result.body);
      } catch {
        /* keep last-good */
      }
    }

    void poll();
    const timer = window.setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;
    let generation = 0;

    function maybeSelect(row: ScoredTransaction) {
      if (row.decision !== "ALLOW") void loadExplanation(row);
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
            if (!selectedId.current && recent[0]) maybeSelect(recent[0]);
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
        if (!selectedId.current) maybeSelect(row);
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
    <div className="console">
      <header className="topbar">
        <div className="brand">
          <div className="radar-icon" aria-hidden="true" />
          <h1>Fraud Radar</h1>
        </div>
        <div className={reconnecting ? "conn-status reconnecting" : "conn-status"}>
          <span className="dot" />
          {reconnecting ? "Reconnecting…" : "Live"}
        </div>
      </header>

      <section className="stats-rail" data-testid="stats-rail" aria-label="System stats">
        <div className="stat">
          <span className="stat-label">Processed</span>
          <span className="stat-value num">{stats ? stats.processed : "—"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Throughput</span>
          <span className="stat-value num">
            {stats ? stats.throughput_tx_per_s : "—"}
            {stats ? <span className="unit">tx/s</span> : null}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Latency p50 / p95</span>
          <span className="stat-value num">
            {formatLatency(stats)}
            {stats ? <span className="unit">ms</span> : null}
          </span>
        </div>
        <div className="stat">
          <span className="stat-label">Flagged</span>
          <span className="stat-value num">{stats ? stats.flagged : "—"}</span>
        </div>
      </section>

      <div className="primary-zone">
        <div className="feed-column">
          <div className="burst-control">
            <div>
              <span className="burst-label">Attack-burst simulator</span>
              <span className="burst-sub">
                Injects a bounded burst of 50 synthetic fraud transactions over 2s, then 30s
                cooldown
              </span>
            </div>
            <button type="button" className="burst-btn" disabled={disabled} onClick={onBurst}>
              {label}
            </button>
          </div>
          {error ? <p className="burst-error">{error}</p> : null}

          <div className="feed-panel">
            <div className="panel-header">
              <h2>Live transaction feed</h2>
              <span className="panel-meta">capped at 50 · newest first</span>
            </div>
            <div className="feed-list" role="log" aria-live="polite" aria-label="Live transaction feed">
              {rows.length > 0 ? (
                rows.map((row) => {
                  const flagged = row.decision !== "ALLOW";
                  const className =
                    selected?.id === row.id ? "feed-row active" : "feed-row";
                  const body = (
                    <>
                      <span className="ts">{formatTime(row.occurred_at)}</span>
                      <span className="amt">${row.amount.toFixed(2)}</span>
                      <span className="score">{row.model_score.toFixed(2)}</span>
                      <span className={`badge ${BADGE[row.decision]}`}>{row.decision}</span>
                    </>
                  );
                  if (flagged) {
                    return (
                      <button
                        key={row.id}
                        type="button"
                        className={className}
                        data-testid="feed-row"
                        onClick={() => void loadExplanation(row)}
                      >
                        {body}
                      </button>
                    );
                  }
                  return (
                    <div key={row.id} className={className} data-testid="feed-row">
                      {body}
                    </div>
                  );
                })
              ) : (
                <div className="feed-empty">
                  <span className="pulse-row">Waiting for transactions…</span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="explain-panel">
          <div className="panel-header">
            <h2>Explainability</h2>
          </div>
          <div className="explain-body">
            {selected ? (
              <>
                <p className="explain-meta">
                  score <span className="num">{selected.model_score.toFixed(2)}</span>
                </p>
                {explaining ? (
                  <div data-testid="explain-skeleton">
                    {Array.from({ length: 5 }, (_, index) => (
                      <div key={index} className="skeleton-bar" />
                    ))}
                  </div>
                ) : (
                  <ul>
                    {explanation.map((item) => {
                      const max = Math.max(...explanation.map((row) => row.contribution), 1e-9);
                      const width = `${Math.round((item.contribution / max) * 100)}%`;
                      return (
                        <li key={item.feature} className="feature-row">
                          <div className="feature-name">
                            <span>{item.feature}</span>
                            <span className="val">{item.contribution.toFixed(2)}</span>
                          </div>
                          <div className="feature-track">
                            <div
                              data-testid="explain-bar"
                              className="feature-fill pos"
                              style={{ width, left: 0 }}
                            />
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </>
            ) : (
              <p className="explain-empty">
                Select a flagged transaction (Review or Blocked) in the feed or alerts table to
                see why it was scored.
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="secondary-zone">
        <div className="charts-row">
          <div className="chart-panel">
            <div className="panel-header">
              <h2>Score distribution</h2>
              <span className="panel-meta">last 200 scored · rolling</span>
            </div>
            <div className="chart-body">
              <canvas data-testid="score-hist" />
            </div>
          </div>
          <div className="chart-panel">
            <div className="panel-header">
              <h2>Fraud rate over time</h2>
              <span className="panel-meta">last 10 min</span>
            </div>
            <div className="chart-body">
              <canvas data-testid="fraud-rate" />
            </div>
          </div>
        </div>

        <div className="alerts-panel">
          <div className="panel-header">
            <h2>Alerts — case review</h2>
          </div>
        </div>
      </div>
    </div>
  );
}
