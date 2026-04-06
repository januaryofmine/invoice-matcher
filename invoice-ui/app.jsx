import { useState, useMemo, useCallback, useEffect } from "react";
import { getHumanReason } from "./humanReason";

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE_OPTIONS = [25, 50, 100];
const DEFAULT_PAGE_SIZE = 50;

const STATUS_CONFIG = {
  AUTO_MATCH:    { label: "Auto-matched",  color: "var(--green)",  dim: "var(--green-dim)",  dot: "#22c55e" },
  LLM_MATCH:     { label: "AI-matched",    color: "var(--accent)", dim: "var(--accent-dim)", dot: "#4f7aff" },
  MANUAL_REVIEW: { label: "Needs review",  color: "var(--yellow)", dim: "var(--yellow-dim)", dot: "#f59e0b" },
  NO_MATCH:      { label: "No match",      color: "var(--muted)",  dim: "transparent",       dot: "#6b7491" },
  NO_PLATE:      { label: "No plate",      color: "var(--orange)", dim: "var(--orange-dim)", dot: "#f97316" },
};

const ALL_STATUSES = Object.keys(STATUS_CONFIG);

const SAMPLE_DATA = [
  { invoice_id: 34921944, status: "MANUAL_REVIEW", matched_delivery_id: null, confidence_score: 0.46, score_gap: 0.0, reason: "score gap 0.000 < threshold, LLM inconclusive", top_candidates: [{ delivery_id: 66979, delivery_name: "Lotte Đà Nẵng", delivery_description: "6 Nại Nam, Hòa Cường Nam, Hải Châu, Đà Nẵng", score: 0.46, reasons: { address_score: 0.46, weight_score: null } }, { delivery_id: 66978, delivery_name: "Bigc Da Nang", delivery_description: "Đà Nẵng, Hải Châu, Đà Nẵng, Việt Nam", score: 0.46, reasons: { address_score: 0.46, weight_score: null } }] },
  { invoice_id: 34922265, status: "AUTO_MATCH", matched_delivery_id: 66983, confidence_score: 0.65, score_gap: 0.36, reason: "score gap 0.36 >= threshold", top_candidates: [{ delivery_id: 66983, delivery_name: "Big C Da Lat", delivery_description: "GO! Đà Lạt, Quảng trường Lâm Viên, Đà Lạt, Lâm Đồng", score: 0.65, reasons: { address_score: 0.65, weight_score: 0.125 } }] },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function ScoreBar({ value, color = "var(--accent)" }) {
  if (value == null)
    return <span style={{ color: "var(--muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>—</span>;
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 100 }}>
      <div style={{ flex: 1, height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2, transition: "width 0.3s ease" }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", minWidth: 28, textAlign: "right" }}>{pct}%</span>
    </div>
  );
}

function Badge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.NO_MATCH;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 9px", borderRadius: 20, background: cfg.dim, border: `1px solid ${cfg.color}22`, color: cfg.color, fontSize: 11, fontWeight: 600, letterSpacing: "0.04em", whiteSpace: "nowrap" }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: cfg.dot, flexShrink: 0 }} />
      {cfg.label}
    </span>
  );
}

function ExpandedDetail({ result }) {
  const cfg = STATUS_CONFIG[result.status] || STATUS_CONFIG.NO_MATCH;
  const human = getHumanReason(result);
  return (
    <div style={{ padding: "16px 20px 16px 48px", borderTop: "1px solid var(--border)", background: "var(--surface2)", display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Context */}
      <div style={{ background: `${cfg.color}11`, border: `1px solid ${cfg.color}33`, borderRadius: 6, padding: "10px 14px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: cfg.color, marginBottom: 5, textTransform: "uppercase" }}>Context</div>
        <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.7 }}>{human.detail}</div>
      </div>

      {/* Candidates */}
      {result.top_candidates?.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--muted)", marginBottom: 8, textTransform: "uppercase" }}>Candidate Deliveries</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {result.top_candidates.map((c, i) => (
              <div key={c.delivery_id} style={{ background: "var(--surface)", border: `1px solid ${i === 0 && result.matched_delivery_id === c.delivery_id ? cfg.color + "55" : "var(--border)"}`, borderRadius: 6, padding: "10px 12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: c.reasons ? 8 : 0 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{c.delivery_name || `Delivery #${c.delivery_id}`}</div>
                    <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 2 }}>{c.delivery_description}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                    {result.matched_delivery_id === c.delivery_id && (
                      <span style={{ fontSize: 10, fontWeight: 700, color: cfg.color, letterSpacing: "0.06em", textTransform: "uppercase" }}>matched</span>
                    )}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text)" }}>
                      {c.score != null ? `${Math.round(c.score * 100)}%` : "—"}
                    </span>
                  </div>
                </div>
                {c.reasons && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px" }}>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>Address</div>
                      <ScoreBar value={c.reasons.address_score} color="var(--accent)" />
                    </div>
                    <div>
                      <div style={{ fontSize: 10, color: "var(--muted)", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>Weight</div>
                      <ScoreBar value={c.reasons.weight_score} color="var(--green)" />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TableRow({ result, expanded, onToggle, index }) {
  const cfg = STATUS_CONFIG[result.status] || STATUS_CONFIG.NO_MATCH;
  const human = getHumanReason(result);
  const top = result.top_candidates?.[0];

  return (
    <>
      <tr
        onClick={onToggle}
        style={{
          background: expanded ? "var(--surface2)" : index % 2 === 0 ? "var(--surface)" : "transparent",
          cursor: "pointer",
          borderBottom: expanded ? "none" : "1px solid var(--border)",
          transition: "background 0.15s",
        }}
      >
        <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap" }}>
          #{result.invoice_id}
        </td>
        <td style={{ padding: "12px 16px" }}>
          <Badge status={result.status} />
        </td>
        <td style={{ padding: "12px 16px", fontSize: 13, color: "var(--text)", maxWidth: 280 }}>
          <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{human.short}</div>
        </td>
        <td style={{ padding: "12px 16px", fontSize: 13, color: "var(--muted)" }}>
          {top ? (
            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>
              {top.delivery_name || `#${top.delivery_id}`}
            </div>
          ) : "—"}
        </td>
        <td style={{ padding: "12px 16px", minWidth: 140 }}>
          <ScoreBar value={result.confidence_score} color={cfg.dot} />
        </td>
        <td style={{ padding: "12px 16px", textAlign: "center", color: "var(--muted)", fontSize: 14, transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "none" }}>
          ↓
        </td>
      </tr>
      {expanded && (
        <tr style={{ borderBottom: "1px solid var(--border)" }}>
          <td colSpan={6} style={{ padding: 0 }} onClick={(e) => e.stopPropagation()}>
            <ExpandedDetail result={result} />
          </td>
        </tr>
      )}
    </>
  );
}

function StatsBar({ data }) {
  const counts = useMemo(() => {
    const c = {};
    ALL_STATUSES.forEach((s) => (c[s] = 0));
    data.forEach((r) => { c[r.status] = (c[r.status] || 0) + 1; });
    return c;
  }, [data]);

  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {ALL_STATUSES.map((s) => {
        const cfg = STATUS_CONFIG[s];
        return (
          <div key={s} style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 20 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: cfg.dot }} />
            <span style={{ color: "var(--muted)", fontSize: 12 }}>{cfg.label}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{counts[s] || 0}</span>
          </div>
        );
      })}
    </div>
  );
}

function Pagination({ page, totalPages, pageSize, onPage, onPageSize, totalItems, from, to }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0", flexWrap: "wrap", gap: 12 }}>
      <div style={{ fontSize: 12, color: "var(--muted)" }}>
        Showing <span style={{ color: "var(--text)", fontWeight: 600 }}>{from}–{to}</span> of{" "}
        <span style={{ color: "var(--text)", fontWeight: 600 }}>{totalItems.toLocaleString()}</span> invoices
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* Page size */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)" }}>
          Rows:
          <select
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 4, padding: "3px 6px", fontSize: 12, cursor: "pointer" }}
          >
            {PAGE_SIZE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        {/* Page nav */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {[
            { label: "«", target: 1, disabled: page === 1 },
            { label: "‹", target: page - 1, disabled: page === 1 },
            { label: "›", target: page + 1, disabled: page === totalPages },
            { label: "»", target: totalPages, disabled: page === totalPages },
          ].map(({ label, target, disabled }) => (
            <button
              key={label}
              onClick={() => !disabled && onPage(target)}
              disabled={disabled}
              style={{
                width: 30, height: 30, borderRadius: 4,
                border: "1px solid var(--border)",
                background: disabled ? "transparent" : "var(--surface)",
                color: disabled ? "var(--border)" : "var(--text)",
                cursor: disabled ? "default" : "pointer",
                fontSize: 14, fontWeight: 600,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              {label}
            </button>
          ))}
          <span style={{ fontSize: 12, color: "var(--muted)", marginLeft: 4 }}>
            Page {page} / {totalPages}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [data, setData] = useState([]);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("AUTO_MATCH");
  const [expandedId, setExpandedId] = useState(null);
  const [fileName, setFileName] = useState("Loading...");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

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
    if (file.size > 50 * 1024 * 1024) { alert("File too large (max 50MB)"); return; }
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        setData(Array.isArray(parsed) ? parsed : []);
        setFileName(file.name);
        setExpandedId(null);
        setPage(1);
      } catch { alert("Invalid JSON file"); }
    };
    reader.readAsText(file);
  }, []);

  const filtered = useMemo(() => {
    return data.filter((r) => {
      const matchStatus = filterStatus === "ALL" || r.status === filterStatus;
      const matchSearch = !search ||
        String(r.invoice_id).includes(search) ||
        r.top_candidates?.some((c) => c.delivery_name?.toLowerCase().includes(search.toLowerCase()));
      return matchStatus && matchSearch;
    });
  }, [data, search, filterStatus]);

  // Reset page when filter/search changes
  useEffect(() => { setPage(1); setExpandedId(null); }, [filterStatus, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const from = filtered.length === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, filtered.length);
  const pageData = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      {/* Header */}
      <div style={{ borderBottom: "1px solid var(--border)", padding: "0 32px" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 32, height: 32, background: "var(--accent)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>🚚</div>
            <div>
              <div style={{ fontWeight: 800, fontSize: 15, letterSpacing: "-0.01em" }}>FreightPilot</div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>Invoice Matching</div>
            </div>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, background: "var(--surface)", border: "1px solid var(--border)", padding: "8px 16px", borderRadius: 6, cursor: "pointer", fontSize: 12, color: "var(--text)" }}>
            <span style={{ fontSize: 14 }}>📂</span>
            Load output.json
            <input type="file" accept=".json" onChange={handleUpload} style={{ display: "none" }} />
          </label>
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px" }}>
        {/* File label */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", marginBottom: 18 }}>
          {fileName} · {data.length.toLocaleString()} invoices
        </div>

        {/* Stats */}
        <div style={{ marginBottom: 22 }}>
          <StatsBar data={data} />
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
          <input
            placeholder="Search invoice ID or delivery name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: 220, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 14px", color: "var(--text)", outline: "none", fontSize: 13 }}
          />
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
            {["ALL", ...ALL_STATUSES].map((s) => {
              const cfg = STATUS_CONFIG[s];
              const active = filterStatus === s;
              return (
                <button
                  key={s}
                  onClick={() => setFilterStatus(s)}
                  style={{
                    padding: "7px 13px", borderRadius: 6, fontSize: 12, fontWeight: 600,
                    border: active ? `1px solid ${cfg?.dot || "var(--accent)"}` : "1px solid var(--border)",
                    background: active ? cfg?.dim || "var(--accent-dim)" : "var(--surface)",
                    color: active ? cfg?.color || "var(--accent)" : "var(--muted)",
                    cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  {s === "ALL" ? "All" : cfg.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Table */}
        <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--surface2)", borderBottom: "1px solid var(--border)" }}>
                  {["Invoice ID", "Status", "Summary", "Top Candidate", "Confidence", ""].map((h, i) => (
                    <th key={i} style={{ padding: "10px 16px", textAlign: "left", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--muted)", textTransform: "uppercase", whiteSpace: "nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageData.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", color: "var(--muted)", padding: "48px 0", fontSize: 14 }}>
                      No invoices match your filters
                    </td>
                  </tr>
                ) : (
                  pageData.map((r, i) => (
                    <TableRow
                      key={r.invoice_id}
                      result={r}
                      index={i}
                      expanded={expandedId === r.invoice_id}
                      onToggle={() => setExpandedId((prev) => prev === r.invoice_id ? null : r.invoice_id)}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        <Pagination
          page={safePage}
          totalPages={totalPages}
          pageSize={pageSize}
          onPage={setPage}
          onPageSize={(n) => { setPageSize(n); setPage(1); }}
          totalItems={filtered.length}
          from={from}
          to={to}
        />
      </div>
    </div>
  );
}
