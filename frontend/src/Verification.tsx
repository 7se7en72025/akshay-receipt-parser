import { useEffect, useState } from "react";
import { LoaderCircle, Sparkles } from "lucide-react";
import { api, message } from "./api";
import type { Document, Health, Notify } from "./types";

interface Check {
  id: string;
  field: string;
  current: string | null;
  observed: string | null;
  page: number;
  status: "match" | "difference" | "unreadable";
  editable: boolean;
}
interface Job {
  id: string;
  model: string;
  document_version: number;
  status: "queued" | "running" | "completed" | "partial" | "failed";
  completed_pages: number;
  stale: boolean;
  outdated: boolean;
  error: string | null;
  result: {
    pages?: {
      page: number;
      printed_date?: string | null;
      reading: {
        supplier_name: string | null;
        bill_number: string | null;
        bill_date: string | null;
        currency: string | null;
        items: {
          description: string | null;
          quantity: string | null;
          unit_price: string | null;
          amount: string | null;
        }[];
      };
    }[];
    total_pages?: number;
    errors?: { page: number; error: string }[];
    report?: {
      checks: Check[];
      notices: string[];
      matched: number;
      differences: number;
      unreadable: number;
      scope: string;
    };
  };
}

function label(path: string) {
  const parts = path.split(".");
  const name = (parts[2] || path).replaceAll("_", " ");
  return parts[0] === "items"
    ? `Item ${Number(parts[1]) + 1}: ${name === "taxable amount" ? "printed amount" : name}`
    : name;
}

export function Verification({
  doc,
  dirty,
  notify,
  onChange,
  onPage,
}: {
  doc: Document;
  dirty: boolean;
  notify: Notify;
  onChange: (doc: Document) => void;
  onPage: (page: number) => void;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [showMatches, setShowMatches] = useState(false);
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [health, jobs] = await Promise.all([
          api<Health>("/health"),
          api<Job[]>(`/documents/${doc.id}/verifications`),
        ]);
        if (cancelled) return;
        setModels(health.vision?.models || []);
        setModel((current) =>
          (health.vision?.models || []).includes(current)
            ? current
            : (health.vision?.models || []).includes(health.vision?.model)
              ? health.vision.model
              : health.vision?.models[0] || "",
        );
        setJob(jobs[0] || null);
        setSelected([]);
      } catch (error) {
        if (!cancelled) setLoadError(message(error));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [doc.id, doc.version]);
  const active = job?.status === "queued" || job?.status === "running";
  useEffect(() => {
    if (!job || !active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const id = job.id;
    async function poll() {
      try {
        const result = await api<Job>(
          `/documents/${doc.id}/verifications/${id}`,
        );
        if (!cancelled) {
          setJob(result);
          setLoadError("");
        }
      } catch (error) {
        if (!cancelled) setLoadError(message(error));
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 2500);
    }
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [doc.id, job?.id, active]);
  async function start() {
    setBusy(true);
    try {
      const result = await api<Job>(`/documents/${doc.id}/verifications`, {
        method: "POST",
        body: JSON.stringify({ version: doc.version, model }),
      });
      setJob(result);
      setSelected([]);
      setLoadError("");
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (
      !job ||
      !window.confirm(
        "Apply the selected AI suggestions to a new saved draft? Check each value against the original bill first. The bill will still need review and approval.",
      )
    )
      return;
    setBusy(true);
    try {
      const result = await api<Document>(
        `/documents/${doc.id}/verifications/${job.id}/apply`,
        {
          method: "POST",
          body: JSON.stringify({ version: doc.version, selected }),
        },
      );
      setSelected([]);
      onChange(result);
      notify(
        "Selected suggestions saved as a draft. Review validation before approval.",
      );
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy(false);
    }
  }
  const stale = !!job && (job.stale || job.document_version !== doc.version);
  const report = job?.result.report;
  const locked = dirty || stale || active || busy || doc.status === "approved";
  return (
    <section className="vision-panel" aria-labelledby="vision-title">
      <div className="section-title">
        <h3 id="vision-title">Verify with AI</h3>
        <Sparkles size={16} />
      </div>
      <p>
        A local vision model reads the original page independently. Compare its
        suggestions with the source before applying them.
      </p>
      <div className="vision-controls">
        <label className="field">
          <span>Local vision model</span>
          <select
            aria-label="Local vision model"
            value={model}
            onChange={(event) => setModel(event.target.value)}
            disabled={active || busy || !models.length}
          >
            {!models.length && <option value="">No model available</option>}
            {models.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button
          className="button secondary small"
          disabled={
            !model ||
            dirty ||
            busy ||
            active ||
            ["queued", "processing", "failed"].includes(doc.status)
          }
          onClick={() => void start()}
        >
          {active || busy ? (
            <LoaderCircle className="spin" size={14} />
          ) : (
            <Sparkles size={14} />
          )}
          {active ? "Checking original…" : "Verify original"}
        </button>
      </div>
      {!models.length && (
        <p>
          Optional local AI is unavailable. Start the configured Ollama runtime
          and install a vision model, then reopen this panel.
        </p>
      )}
      {dirty && (
        <div className="info-note">
          Save your edits before verifying or applying suggestions.
        </div>
      )}
      {loadError && <p role="alert">{loadError}</p>}
      {job && (
        <p aria-live="polite">
          {job.model} · Draft version {job.document_version} · {job.status} ·{" "}
          {job.result.pages?.length || 0}/
          {job.result.total_pages || doc.page_count} pages read
        </p>
      )}
      {active && (
        <p>
          You can leave this panel while the check runs. Large pages may take
          several minutes.
        </p>
      )}
      {stale && (
        <div className="info-note">
          This report belongs to an older draft or uses older AI reading
          settings. Run verification again before applying suggestions.
        </div>
      )}
      {job?.error && <div className="info-note">{job.error}</div>}
      {job?.result.errors?.map((entry) => (
        <p key={entry.page}>
          Page {entry.page}: {entry.error}
        </p>
      ))}
      {report && (
        <>
          <p>
            <strong>{report.matched}</strong> agreements ·{" "}
            <strong>{report.differences}</strong> differences ·{" "}
            <strong>{report.unreadable}</strong> unreadable fields
          </p>
          <p>{report.scope}</p>
          <label className="vision-show-matches">
            <input
              type="checkbox"
              checked={showMatches}
              onChange={(event) => setShowMatches(event.target.checked)}
            />
            Show agreeing fields
          </label>
          <div className="vision-comparisons">
            {report.checks
              .filter((check) => showMatches || check.status !== "match")
              .map((check) => (
                <div className={`vision-check ${check.status}`} key={check.id}>
                  <label>
                    <input
                      type="checkbox"
                      aria-label={`Apply ${label(check.field)} from page ${check.page}`}
                      disabled={locked || !check.editable}
                      checked={selected.includes(check.id)}
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, check.id]
                            : current.filter((id) => id !== check.id),
                        )
                      }
                    />
                    <strong>{label(check.field)}</strong>
                    <span>{check.status}</span>
                  </label>
                  <dl>
                    <div>
                      <dt>Saved draft</dt>
                      <dd>{check.current ?? "Not recorded"}</dd>
                    </div>
                    <div>
                      <dt>AI reading</dt>
                      <dd>{check.observed ?? "Not readable"}</dd>
                    </div>
                  </dl>
                  <button
                    className="text-button"
                    onClick={() => onPage(check.page)}
                  >
                    Inspect original page {check.page}
                  </button>
                </div>
              ))}
          </div>
          {report.notices.length > 0 && (
            <details>
              <summary>
                {report.notices.length} items need manual review
              </summary>
              <ul>
                {report.notices.map((notice) => (
                  <li key={notice}>{notice}</li>
                ))}
              </ul>
            </details>
          )}
          {!!job?.result.pages?.length && (
            <details className="vision-readings">
              <summary>
                Independent AI page readings ({job.result.pages.length})
              </summary>
              <p>
                Read-only model output. These rows have not been saved to your
                draft. Check the original before adding or changing any entry.
              </p>
              {job.result.pages.map((entry) => (
                <section key={entry.page}>
                  <button
                    className="text-button"
                    onClick={() => onPage(entry.page)}
                  >
                    Inspect original page {entry.page}
                  </button>
                  <p>
                    {entry.reading.supplier_name || "Seller unreadable"} ·{" "}
                    {entry.reading.bill_number || "Bill number unreadable"} ·{" "}
                    {entry.reading.currency || "Currency unclear"}
                  </p>
                  <p>
                    Printed date:{" "}
                    {entry.printed_date ||
                      entry.reading.bill_date ||
                      "Not readable"}
                    {!entry.reading.bill_date && entry.printed_date
                      ? " (requires manual interpretation)"
                      : ""}
                  </p>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>AI description</th>
                          <th>Quantity</th>
                          <th>Printed unit rate</th>
                          <th>Printed line amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        {entry.reading.items.map((item, index) => (
                          <tr key={index}>
                            <td>{item.description || "Not readable"}</td>
                            <td>
                              {item.quantity ?? "Not printed / unreadable"}
                            </td>
                            <td>
                              {item.unit_price ?? "Not printed / unreadable"}
                            </td>
                            <td>{item.amount ?? "Not printed / unreadable"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {!entry.reading.items.length && (
                    <p>No product rows were independently read on this page.</p>
                  )}
                </section>
              ))}
            </details>
          )}
          <button
            className="button secondary small"
            disabled={
              locked ||
              !selected.length ||
              !["completed", "partial"].includes(job!.status)
            }
            onClick={() => void apply()}
          >
            Apply {selected.length || "selected"} suggestions to draft
          </button>
        </>
      )}
    </section>
  );
}
