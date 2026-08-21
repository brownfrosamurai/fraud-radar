import { useEffect, useRef, useState } from "react";
import {
  fetchAlerts,
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
import { accountChrome } from "./account";
import { drawHistogram, drawRate, pushRate, pushScore, type RateBucket } from "./charts";
import { nextReconnectDelay } from "./reconnect";

type AlertFilter = "all" | "review" | "block";
type AlertSort = "created_at" | "amount" | "model_score" | "decision";
type AlertDir = "asc" | "desc";

const LIVE_CAP = 50;
const ALERT_PAGE_SIZE = 50;
const EXPLAIN_TIP =
  "Permutation importance on Isolation Forest. Each bar is how much the score dropped when that feature was shuffled. Larger bars mattered more for this Review or Block. This is not SHAP.";

const SORT_HEADERS: { key: AlertSort; label: string }[] = [
  { key: "created_at", label: "Time" },
  { key: "amount", label: "Amount" },
  { key: "model_score", label: "Score" },
  { key: "decision", label: "Decision" },
];

const BADGE: Record<Decision, string> = {
  ALLOW: "allow",
  REVIEW: "review",
  BLOCK: "block",
};

const DECISION_LABEL: Record<Decision, string> = {
  ALLOW: "Approved",
  REVIEW: "Review",
  BLOCK: "Blocked",
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
    .slice(0, LIVE_CAP);
}

function formatLatency(stats: Stats | null): string {
  if (!stats || stats.latency_p50_ms === null || stats.latency_p95_ms === null) return "—";
  return `${stats.latency_p50_ms} / ${stats.latency_p95_ms}`;
}

function formatTime(iso: string): string {
  return new Date(iso).toISOString().slice(11, 19);
}

function matchesAlertFilter(row: ScoredTransaction, filter: AlertFilter): boolean {
  if (filter === "review") return row.decision === "REVIEW";
  if (filter === "block") return row.decision === "BLOCK";
  return row.decision !== "ALLOW";
}

function mergeAlertPage(
  current: ScoredTransaction[],
  pageItems: ScoredTransaction[],
  offset: number,
  filter: AlertFilter,
): ScoredTransaction[] {
  if (offset !== 0) return pageItems.slice(0, ALERT_PAGE_SIZE);
  const pageIds = new Set(pageItems.map((row) => row.id));
  const liveOnly = current.filter(
    (row) => !pageIds.has(row.id) && matchesAlertFilter(row, filter),
  );
  return [...liveOnly, ...pageItems].slice(0, ALERT_PAGE_SIZE);
}

function alertsRangeLabel(offset: number, shown: number, total: number): string {
  if (total === 0 || shown === 0) return `Showing 0 of ${total}`;
  return `Showing ${offset + 1}–${offset + shown} of ${total}`;
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
  const [alertFilter, setAlertFilter] = useState<AlertFilter>("all");
  const [alertSort, setAlertSort] = useState<AlertSort>("created_at");
  const [alertDir, setAlertDir] = useState<AlertDir>("desc");
  const [alertOffset, setAlertOffset] = useState(0);
  const [alertItems, setAlertItems] = useState<ScoredTransaction[]>([]);
  const [alertTotal, setAlertTotal] = useState(0);
  const [alertsError, setAlertsError] = useState(false);
  const [alertsEpoch, setAlertsEpoch] = useState(0);
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const selectedId = useRef<string | null>(null);
  const alertFilterRef = useRef(alertFilter);
  const alertOffsetRef = useRef(alertOffset);
  const histCanvasRef = useRef<HTMLCanvasElement>(null);
  const rateCanvasRef = useRef<HTMLCanvasElement>(null);
  const scoresRef = useRef<number[]>([]);
  const bucketsRef = useRef<RateBucket[]>([]);
  alertFilterRef.current = alertFilter;
  alertOffsetRef.current = alertOffset;

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

    async function load() {
      try {
        const result = await fetchAlerts({
          filter: alertFilter,
          sort: alertSort,
          dir: alertDir,
          offset: alertOffset,
          limit: ALERT_PAGE_SIZE,
        });
        if (cancelled) return;
        if (result.status === 200 && result.body) {
          const page = result.body;
          setAlertItems((current) => {
            const merged = mergeAlertPage(current, page.items, alertOffset, alertFilter);
            setAlertTotal(
              alertOffset === 0 ? Math.max(page.total, merged.length) : page.total,
            );
            return merged;
          });
          setAlertsError(false);
        } else {
          setAlertsError(true);
        }
        setAlertsLoaded(true);
      } catch {
        if (!cancelled) {
          setAlertsError(true);
          setAlertsLoaded(true);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [alertFilter, alertSort, alertDir, alertOffset, alertsEpoch]);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempt = 0;
    let generation = 0;

    function maybeSelect(row: ScoredTransaction) {
      if (row.decision !== "ALLOW") void loadExplanation(row);
    }

    function ingestCharts(row: ScoredTransaction) {
      scoresRef.current = pushScore(scoresRef.current, row.model_score);
      bucketsRef.current = pushRate(
        bucketsRef.current,
        Date.parse(row.occurred_at),
        row.decision !== "ALLOW",
      );
      if (histCanvasRef.current) drawHistogram(histCanvasRef.current, scoresRef.current);
      if (rateCanvasRef.current) drawRate(rateCanvasRef.current, bucketsRef.current);
    }

    function ingestFlaggedAlert(row: ScoredTransaction) {
      if (!matchesAlertFilter(row, alertFilterRef.current)) return;
      if (alertOffsetRef.current !== 0) {
        setAlertTotal((total) => total + 1);
        return;
      }
      setAlertItems((current) => {
        if (current.some((item) => item.id === row.id)) return current;
        setAlertTotal((total) => total + 1);
        return [row, ...current].slice(0, ALERT_PAGE_SIZE);
      });
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
        ingestCharts(row);
        setRows((current) => mergeNewest(current, [row]));
        if (row.decision !== "ALLOW") ingestFlaggedAlert(row);
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
  const alertsShown = alertItems.length;
  const canPrev = alertOffset > 0;
  const canNext = alertOffset + ALERT_PAGE_SIZE < alertTotal;

  function onAlertSort(column: AlertSort) {
    if (column === alertSort) {
      setAlertDir((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setAlertSort(column);
    }
    setAlertOffset(0);
  }

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
              <span className="panel-meta">capped at {LIVE_CAP} · newest first</span>
            </div>
            <div className="feed-list" role="log" aria-live="polite" aria-label="Live transaction feed">
              {rows.length > 0 ? (
                rows.map((row) => {
                  const flagged = row.decision !== "ALLOW";
                  const className =
                    selected?.id === row.id ? "feed-row active" : "feed-row";
                  const account = accountChrome(row.id);
                  const body = (
                    <>
                      <span className="ts">{formatTime(row.occurred_at)}</span>
                      <span className="method">{account.line}</span>
                      <span className="amt">${row.amount.toFixed(2)}</span>
                      <span className="score">{row.model_score.toFixed(2)}</span>
                      <span className={`badge ${BADGE[row.decision]}`}>
                        {DECISION_LABEL[row.decision]}
                      </span>
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
            <div className="explain-title">
              <h2>Explainability</h2>
              <button
                type="button"
                className="tip-btn"
                aria-label="What explainability shows"
                aria-describedby="explain-tooltip"
              >
                i
              </button>
              <span id="explain-tooltip" role="tooltip" className="tip-bubble">
                {EXPLAIN_TIP}
              </span>
            </div>
            {selected ? (
              <span className="panel-meta">
                ${selected.amount.toFixed(2)} · {formatTime(selected.occurred_at)}
              </span>
            ) : null}
          </div>
          <div className="explain-body" data-testid="explain-body">
            {selected ? (
              <>
                <div className="explain-decision">
                  <span className={`badge ${BADGE[selected.decision]}`}>
                    {DECISION_LABEL[selected.decision]}
                  </span>
                </div>
                <p className="explain-meta">
                  score <span className="num">{selected.model_score.toFixed(3)}</span>
                  {" · "}
                  {accountChrome(selected.id).line}
                  <br />
                  feature contribution to risk score
                </p>
                {explaining ? (
                  <div data-testid="explain-skeleton">
                    {["70%", "55%", "80%", "40%"].map((width) => (
                      <div key={width} className="skeleton-bar" style={{ width }} />
                    ))}
                  </div>
                ) : (
                  <ul>
                    {explanation.map((item) => {
                      const max = Math.max(
                        ...explanation.map((row) => Math.abs(row.contribution)),
                        1e-9,
                      );
                      const width = `${Math.round((Math.abs(item.contribution) / max) * 50)}%`;
                      const side = item.contribution >= 0 ? "pos" : "neg";
                      const signed =
                        item.contribution >= 0
                          ? `+${item.contribution.toFixed(3)}`
                          : item.contribution.toFixed(3);
                      return (
                        <li key={item.feature} className="feature-row">
                          <div className="feature-name">
                            <span>{item.feature}</span>
                            <span className="val">{signed}</span>
                          </div>
                          <div className="feature-track">
                            <div
                              data-testid="explain-bar"
                              className={`feature-fill ${side}`}
                              style={{ width }}
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
              <canvas ref={histCanvasRef} data-testid="score-hist" width={640} height={160} />
              <p className="chart-note">
                Isolation Forest scores from 0 to 1. Blue is below 0.40 (Approved), amber is the
                Review band, red is Block. Dotted lines mark the 0.40 / 0.60 / 0.90 thresholds.
              </p>
            </div>
          </div>
          <div className="chart-panel">
            <div className="panel-header">
              <h2>Fraud rate over time</h2>
              <span className="panel-meta">last 10 min</span>
            </div>
            <div className="chart-body">
              <canvas ref={rateCanvasRef} data-testid="fraud-rate" width={640} height={160} />
              <p className="chart-note">
                Share of Review and Blocked transactions in each 10-second bucket over the last 10
                minutes. Spikes are burst traffic or a cluster of high scores.
              </p>
            </div>
          </div>
        </div>

        <div className="alerts-panel">
          <div className="panel-header">
            <h2>Alerts — case review</h2>
            <div className="alerts-controls">
              <span className="panel-meta">{ALERT_PAGE_SIZE} per page · newest first</span>
              <label htmlFor="alerts-filter">Filter</label>
              <select
                id="alerts-filter"
                className="alerts-filter"
                aria-label="Alert filter"
                value={alertFilter}
                onChange={(event) => {
                  setAlertFilter(event.target.value as AlertFilter);
                  setAlertOffset(0);
                }}
              >
                <option value="all">All flagged</option>
                <option value="review">Review only</option>
                <option value="block">Blocked only</option>
              </select>
            </div>
          </div>
          <div className="alerts-table-wrap" data-testid="alerts-table-wrap">
            <table className="alerts-table">
              <thead>
                <tr>
                  {SORT_HEADERS.flatMap((header) => {
                    const arrow =
                      alertSort === header.key ? (alertDir === "asc" ? " ↑" : " ↓") : "";
                    const cell = (
                      <th key={header.key} scope="col" onClick={() => onAlertSort(header.key)}>
                        <button type="button">
                          {header.label}
                          <span className="arrow">{arrow}</span>
                        </button>
                      </th>
                    );
                    if (header.key !== "created_at") return [cell];
                    return [
                      cell,
                      <th key="source-ip" scope="col" className="alerts-source-ip">
                        Source IP
                      </th>,
                    ];
                  })}
                </tr>
              </thead>
              <tbody>
                {alertItems.length > 0 ? (
                  alertItems.map((row) => (
                    <tr
                      key={row.id}
                      className={selected?.id === row.id ? "clickable active" : "clickable"}
                      onClick={() => void loadExplanation(row)}
                    >
                      <td className="num">{formatTime(row.occurred_at)}</td>
                      <td className="num">{accountChrome(row.id).ip}</td>
                      <td className="amt">${row.amount.toFixed(2)}</td>
                      <td className="score">{row.model_score.toFixed(2)}</td>
                      <td>
                        <span className={`badge ${BADGE[row.decision]}`}>
                          {DECISION_LABEL[row.decision]}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : !alertsLoaded && !alertsError ? (
                  <tr className="alerts-empty" data-testid="alerts-skeleton">
                    <td colSpan={5}>
                      {["70%", "55%", "80%", "40%"].map((width) => (
                        <div key={width} className="skeleton-bar" style={{ width }} />
                      ))}
                    </td>
                  </tr>
                ) : (
                  <tr className="alerts-empty">
                    <td colSpan={5}>{alertsError ? null : "No flagged transactions yet"}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="alerts-footer">
            <span data-testid="alerts-shown">
              {alertsRangeLabel(alertOffset, alertsShown, alertTotal)}
            </span>
            <div className="alerts-footer-actions">
              {alertsLoaded ? (
                <>
                  <button
                    type="button"
                    disabled={!canPrev}
                    aria-label="Previous 50 alerts"
                    onClick={() =>
                      setAlertOffset((current) => Math.max(0, current - ALERT_PAGE_SIZE))
                    }
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={!canNext}
                    aria-label="Next 50 alerts"
                    onClick={() => setAlertOffset((current) => current + ALERT_PAGE_SIZE)}
                  >
                    Next
                  </button>
                </>
              ) : null}
              {alertsError ? (
                <button type="button" onClick={() => setAlertsEpoch((n) => n + 1)}>
                  Retry
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
