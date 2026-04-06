import { useState, useMemo, useCallback, useEffect } from "react";
import { getHumanReason } from "./humanReason";

// ── Status config ──────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  AUTO_MATCH: {
    label: "Auto-matched",
    color: "var(--green)",
    dim: "var(--green-dim)",
    dot: "#22c55e",
  },
  LLM_MATCH: {
    label: "AI-matched",
    color: "var(--accent)",
    dim: "var(--accent-dim)",
    dot: "#4f7aff",
  },
  MANUAL_REVIEW: {
    label: "Needs review",
    color: "var(--yellow)",
    dim: "var(--yellow-dim)",
    dot: "#f59e0b",
  },
  NO_MATCH: {
    label: "No match",
    color: "var(--muted)",
    dim: "transparent",
    dot: "#6b7491",
  },
  NO_PLATE: {
    label: "No plate",
    color: "var(--orange)",
    dim: "var(--orange-dim)",
    dot: "#f97316",
  },
};

const ALL_STATUSES = Object.keys(STATUS_CONFIG);

// ── Mock sample data (replaced by uploaded output.json) ───────────────────────

const SAMPLE_DATA = [
  {
    invoice_id: 34921944,
    status: "MANUAL_REVIEW",
    matched_delivery_id: null,
    confidence_score: 0.46,
    score_gap: 0.0,
    reason: "score gap 0.000 < threshold, LLM inconclusive",
    top_candidates: [
      {
        delivery_id: 66979,
        delivery_name: "Lotte Đà Nẵng",
        delivery_description: "6 Nại Nam, Hòa Cường Nam, Hải Châu, Đà Nẵng",
        score: 0.46,
        reasons: { address_score: 0.46, weight_score: null },
      },
      {
        delivery_id: 66978,
        delivery_name: "Bigc Da Nang",
        delivery_description: "Đà Nẵng, Hải Châu, Đà Nẵng, Việt Nam",
        score: 0.46,
        reasons: { address_score: 0.46, weight_score: null },
      },
    ],
  },
  {
    invoice_id: 34922265,
    status: "AUTO_MATCH",
    matched_delivery_id: 66983,
    confidence_score: 0.65,
    score_gap: 0.36,
    reason: "score gap 0.36 >= threshold",
    top_candidates: [
      {
        delivery_id: 66983,
        delivery_name: "Big C Da Lat",
        delivery_description:
          "GO! Đà Lạt, Quảng trường Lâm Viên, Đà Lạt, Lâm Đồng",
        score: 0.65,
        reasons: { address_score: 0.65, weight_score: 0.125 },
      },
      {
        delivery_id: 66982,
        delivery_name: "CÔNG TY TNHH NGỌC TRƯƠNG",
        delivery_description: "26 Đường Trần Khánh Dư, Phường 8, Đà Lạt",
        score: 0.29,
        reasons: { address_score: 0.29, weight_score: 0.03 },
      },
    ],
  },
  {
    invoice_id: 34919782,
    status: "NO_MATCH",
    matched_delivery_id: null,
    confidence_score: null,
    score_gap: null,
    reason: "plate matches but invoice date outside delivery window",
    top_candidates: [],
  },
  {
    invoice_id: 34917426,
    status: "NO_PLATE",
    matched_delivery_id: null,
    confidence_score: null,
    score_gap: null,
    reason: "missing truck plate",
    top_candidates: [],
  },
  {
    invoice_id: 34922293,
    status: "AUTO_MATCH",
    matched_delivery_id: 66985,
    confidence_score: 0.53,
    score_gap: 0.42,
    reason: "score gap 0.42 >= threshold",
    top_candidates: [
      {
        delivery_id: 66985,
        delivery_name: "Big C Quảng Ngãi",
        delivery_description:
          "KFC Big C Quảng Ngãi, Lý Thường Kiệt, Nghĩa Chánh, Quảng Ngãi",
        score: 0.53,
        reasons: { address_score: 0.53, weight_score: null },
      },
      {
        delivery_id: 66984,
        delivery_name: "Tuan Viet",
        delivery_description: "Tịnh ấn Tây, Sơn Tịnh, Quảng Ngãi",
        score: 0.11,
        reasons: { address_score: 0.11, weight_score: null },
      },
    ],
  },
];

// ── Score bar ──────────────────────────────────────────────────────────────────

function ScoreBar({ value, color = "var(--accent)" }) {
  if (value === null || value === undefined)
    return (
      <span
        style={{
          color: "var(--muted)",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
        }}
      >
        —
      </span>
    );
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 4,
          background: "var(--border)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 2,
            transition: "width 0.4s ease",
          }}
        />
      </div>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          color: "var(--muted)",
          minWidth: 32,
          textAlign: "right",
        }}
      >
        {pct}%
      </span>
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.NO_MATCH;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 20,
        background: cfg.dim,
        border: `1px solid ${cfg.color}22`,
        color: cfg.color,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.04em",
        whiteSpace: "nowrap",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: cfg.dot,
          flexShrink: 0,
        }}
      />
      {cfg.label}
    </span>
  );
}

// ── Invoice row / card ────────────────────────────────────────────────────────

function InvoiceCard({ result, expanded, onToggle }) {
  const cfg = STATUS_CONFIG[result.status] || STATUS_CONFIG.NO_MATCH;
  const human = getHumanReason(result);
  const top = result.top_candidates?.[0];

  return (
    <div
      onClick={onToggle}
      style={{
        background: expanded ? "var(--surface2)" : "var(--surface)",
        border: `1px solid ${expanded ? cfg.color + "44" : "var(--border)"}`,
        borderRadius: 10,
        overflow: "hidden",
        cursor: "pointer",
        transition: "border-color 0.2s, background 0.2s",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 160px 120px 40px",
          alignItems: "center",
          gap: 16,
          padding: "14px 20px",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              color: "var(--muted)",
              marginBottom: 2,
            }}
          >
            #{result.invoice_id}
          </div>
          <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 600 }}>
            {human.short}
          </div>
        </div>
        <div>
          {result.confidence_score !== null &&
          result.confidence_score !== undefined ? (
            <ScoreBar value={result.confidence_score} color={cfg.dot} />
          ) : (
            <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>
          )}
        </div>
        <div>
          <Badge status={result.status} />
        </div>
        <div
          style={{
            color: "var(--muted)",
            fontSize: 18,
            textAlign: "center",
            transform: expanded ? "rotate(180deg)" : "none",
            transition: "transform 0.2s",
          }}
        >
          ↓
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            borderTop: `1px solid var(--border)`,
            padding: "16px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Human context */}
          <div
            style={{
              background: `${cfg.color}11`,
              border: `1px solid ${cfg.color}33`,
              borderRadius: 6,
              padding: "12px 16px",
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.08em",
                color: cfg.color,
                marginBottom: 6,
                textTransform: "uppercase",
              }}
            >
              Context
            </div>
            <div
              style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.7 }}
            >
              {human.detail}
            </div>
          </div>

          {/* Candidates */}
          {result.top_candidates?.length > 0 && (
            <div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  color: "var(--muted)",
                  marginBottom: 10,
                  textTransform: "uppercase",
                }}
              >
                Candidate Deliveries
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {result.top_candidates.map((c, i) => (
                  <div
                    key={c.delivery_id}
                    style={{
                      background: "var(--surface)",
                      border: `1px solid ${i === 0 && result.matched_delivery_id === c.delivery_id ? cfg.color + "55" : "var(--border)"}`,
                      borderRadius: 6,
                      padding: "12px 14px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: 12,
                        marginBottom: 8,
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 13 }}>
                          {c.delivery_name || `Delivery #${c.delivery_id}`}
                        </div>
                        <div
                          style={{
                            color: "var(--muted)",
                            fontSize: 12,
                            marginTop: 2,
                          }}
                        >
                          {c.delivery_description}
                        </div>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexShrink: 0,
                        }}
                      >
                        {result.matched_delivery_id === c.delivery_id && (
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              color: cfg.color,
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                            }}
                          >
                            matched
                          </span>
                        )}
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 13,
                            color: "var(--text)",
                          }}
                        >
                          {c.score !== undefined
                            ? `${Math.round(c.score * 100)}%`
                            : "—"}
                        </span>
                      </div>
                    </div>
                    {c.reasons && (
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: "6px 16px",
                        }}
                      >
                        <div>
                          <div
                            style={{
                              fontSize: 10,
                              color: "var(--muted)",
                              marginBottom: 3,
                              textTransform: "uppercase",
                              letterSpacing: "0.06em",
                            }}
                          >
                            Address
                          </div>
                          <ScoreBar
                            value={c.reasons.address_score}
                            color="var(--accent)"
                          />
                        </div>
                        <div>
                          <div
                            style={{
                              fontSize: 10,
                              color: "var(--muted)",
                              marginBottom: 3,
                              textTransform: "uppercase",
                              letterSpacing: "0.06em",
                            }}
                          >
                            Weight
                          </div>
                          <ScoreBar
                            value={c.reasons.weight_score}
                            color="var(--green)"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Stats bar ─────────────────────────────────────────────────────────────────

function StatsBar({ data }) {
  const counts = useMemo(() => {
    const c = {};
    ALL_STATUSES.forEach((s) => (c[s] = 0));
    data.forEach((r) => {
      c[r.status] = (c[r.status] || 0) + 1;
    });
    return c;
  }, [data]);

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      {ALL_STATUSES.map((s) => {
        const cfg = STATUS_CONFIG[s];
        return (
          <div
            key={s}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 14px",
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 20,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: cfg.dot,
              }}
            />
            <span style={{ color: "var(--muted)", fontSize: 12 }}>
              {cfg.label}
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                fontWeight: 600,
                color: "var(--text)",
              }}
            >
              {counts[s] || 0}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [data, setData] = useState([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [expandedId, setExpandedId] = useState(null);
  const [fileName, setFileName] = useState("Loading...");

  useEffect(() => {
    const url = import.meta.env.PROD ? "/api/output" : "/output.json";
    fetch(url)
      .then((r) => r.json())
      .then((parsed) => {
        setData(Array.isArray(parsed) ? parsed : []);
        setFileName("output.json");
      })
      .catch(() => {
        setData(SAMPLE_DATA);
        setFileName("Sample data (fallback)");
      });
  }, []);

  const handleUpload = useCallback((e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        setData(Array.isArray(parsed) ? parsed : []);
        setFileName(file.name);
        setExpandedId(null);
      } catch {
        alert("Invalid JSON file");
      }
    };
    reader.readAsText(file);
  }, []);

  const filtered = useMemo(() => {
    return data.filter((r) => {
      const matchStatus = filterStatus === "ALL" || r.status === filterStatus;
      const matchSearch =
        !search ||
        String(r.invoice_id).includes(search) ||
        r.top_candidates?.some((c) =>
          c.delivery_name?.toLowerCase().includes(search.toLowerCase()),
        );
      return matchStatus && matchSearch;
    });
  }, [data, search, filterStatus]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      {/* Header */}
      <div
        style={{ borderBottom: "1px solid var(--border)", padding: "0 32px" }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 64,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 32,
                height: 32,
                background: "var(--accent)",
                borderRadius: 8,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 16,
              }}
            >
              🚚
            </div>
            <div>
              <div
                style={{
                  fontWeight: 800,
                  fontSize: 15,
                  letterSpacing: "-0.01em",
                }}
              >
                FreightPilot
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                Invoice Matching
              </div>
            </div>
          </div>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 12,
              color: "var(--text)",
              transition: "border-color 0.2s",
            }}
          >
            <span style={{ fontSize: 14 }}>📂</span>
            Load output.json
            <input
              type="file"
              accept=".json"
              onChange={handleUpload}
              style={{ display: "none" }}
            />
          </label>
        </div>
      </div>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 32px" }}>
        {/* File label */}
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--muted)",
            marginBottom: 20,
          }}
        >
          {fileName} · {data.length.toLocaleString()} invoices
        </div>

        {/* Stats */}
        <div style={{ marginBottom: 24 }}>
          <StatsBar data={data} />
        </div>

        {/* Filters */}
        <div
          style={{
            display: "flex",
            gap: 10,
            marginBottom: 24,
            flexWrap: "wrap",
          }}
        >
          <input
            placeholder="Search invoice ID or delivery name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              flex: 1,
              minWidth: 220,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "9px 14px",
              color: "var(--text)",
              outline: "none",
            }}
          />
          <div style={{ display: "flex", gap: 6 }}>
            {["ALL", ...ALL_STATUSES].map((s) => {
              const cfg = STATUS_CONFIG[s];
              const active = filterStatus === s;
              return (
                <button
                  key={s}
                  onClick={() => setFilterStatus(s)}
                  style={{
                    padding: "8px 14px",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    border: active
                      ? `1px solid ${cfg?.dot || "var(--accent)"}`
                      : "1px solid var(--border)",
                    background: active
                      ? cfg?.dim || "var(--accent-dim)"
                      : "var(--surface)",
                    color: active
                      ? cfg?.color || "var(--accent)"
                      : "var(--muted)",
                    transition: "all 0.15s",
                  }}
                >
                  {s === "ALL" ? "All" : cfg.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Results count */}
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>
          Showing {filtered.length.toLocaleString()} of{" "}
          {data.length.toLocaleString()} invoices
        </div>

        {/* Column headers */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 160px 120px 40px",
            gap: 16,
            padding: "6px 20px",
            marginBottom: 8,
          }}
        >
          {["Invoice", "Confidence", "Status", ""].map((h, i) => (
            <div
              key={i}
              style={{
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.08em",
                color: "var(--muted)",
                textTransform: "uppercase",
              }}
            >
              {h}
            </div>
          ))}
        </div>

        {/* Invoice list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {filtered.length === 0 ? (
            <div
              style={{
                textAlign: "center",
                color: "var(--muted)",
                padding: "48px 0",
                fontSize: 14,
              }}
            >
              No invoices match your filters
            </div>
          ) : (
            filtered.map((r) => (
              <InvoiceCard
                key={r.invoice_id}
                result={r}
                expanded={expandedId === r.invoice_id}
                onToggle={() =>
                  setExpandedId((prev) =>
                    prev === r.invoice_id ? null : r.invoice_id,
                  )
                }
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
