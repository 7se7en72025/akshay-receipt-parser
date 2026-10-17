import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  HardDrive,
  Inbox,
  LayoutGrid,
  LoaderCircle,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { api, day, message, money } from "./api";
import { Loading, Modal, Status } from "./components";
import { Review } from "./Review";
import { Templates } from "./Templates";
import type {
  Document,
  DocumentSummary,
  InboxPage,
  UploadResult,
  ExportRecord,
  Health,
  Template,
} from "./types";
import { UploadReport } from "./UploadReport";

type View = "invoices" | "templates" | "exports";
export default function App() {
  const [view, setView] = useState<View>("invoices");
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [reviewQueue, setReviewQueue] = useState<DocumentSummary[]>([]);
  const [inbox, setInbox] = useState<InboxPage | null>(null);
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [order, setOrder] = useState("newest");
  const [query, setQuery] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [showUploads, setShowUploads] = useState(false);
  const refreshSequence = useRef(0);
  const inFlight = useRef<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [activeError, setActiveError] = useState("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [useAi, setUseAi] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<Document | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const [selected, setSelected] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [help, setHelp] = useState(false);
  const [exporting, setExporting] = useState<string[] | null>(null);
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  const input = useRef<HTMLInputElement>(null);
  const notify = useCallback(
    (text: string, error = false) => setToast({ text, error }),
    [],
  );
  const refresh = useCallback(async () => {
    if (dateFrom && dateTo && dateFrom > dateTo) {
      setLoading(false);
      return;
    }
    const params = new URLSearchParams({
      search: query,
      status: filter,
      page: String(page),
      order,
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    });
    const key = params.toString();
    if (inFlight.current === key) return;
    inFlight.current = key;
    const sequence = ++refreshSequence.current;
    try {
      const result = await api<InboxPage>("/inbox?" + params);
      if (sequence !== refreshSequence.current) return;
      setDocuments(result.items);
      setInbox(result);
      if (result.page !== page) setPage(result.page);
      setSelected((current) =>
        current.filter(
          (id) =>
            !result.items.some(
              (doc) => doc.id === id && doc.status !== "approved",
            ),
        ),
      );
      setConnectionError("");
    } catch (error) {
      if (sequence === refreshSequence.current)
        setConnectionError(message(error));
    } finally {
      if (sequence === refreshSequence.current) {
        inFlight.current = null;
        setLoading(false);
      }
    }
  }, [query, filter, page, dateFrom, dateTo, order]);
  const refreshTemplates = useCallback(async () => {
    try {
      setTemplates(await api<Template[]>("/templates"));
    } catch (error) {
      notify(message(error), true);
    }
  }, [notify]);
  const refreshExports = useCallback(async () => {
    try {
      setExports(await api<ExportRecord[]>("/exports"));
    } catch (error) {
      notify(message(error), true);
    }
  }, [notify]);
  useEffect(() => {
    void refreshTemplates();
    void refreshExports();
    void api<Health>("/health")
      .then(setHealth)
      .catch(() => {});
  }, [refreshTemplates, refreshExports]);
  useEffect(() => {
    setLoading(true);
    void refresh();
    const timer = setInterval(() => {
      void refresh();
      const doc = activeRef.current;
      if (doc && ["queued", "processing"].includes(doc.status)) {
        void api<Document>("/documents/" + doc.id)
          .then((result) => {
            if (activeRef.current?.id === result.id) setActive(result);
          })
          .catch(() => {});
      }
    }, 2500);
    return () => {
      clearInterval(timer);
      refreshSequence.current++;
      inFlight.current = null;
    };
  }, [refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    setActive(null);
    setActiveError("");
    if (!activeId) return;
    let canceled = false;
    void api<Document>("/documents/" + activeId)
      .then((doc) => {
        if (!canceled) setActive(doc);
      })
      .catch((error) => {
        if (!canceled) setActiveError(message(error));
      });
    return () => {
      canceled = true;
    };
  }, [activeId, notify]);

  async function upload(files: FileList | File[]) {
    if (!files.length || uploading) return;
    const batch = Array.from(files);
    if (
      batch.length > 12 ||
      batch.some((file) => file.size > 15 * 1024 * 1024 || file.size === 0) ||
      batch.reduce((sum, file) => sum + file.size, 0) > 60 * 1024 * 1024
    ) {
      notify(
        "Choose 1–12 non-empty files, up to 15 MB each and 60 MB in total.",
        true,
      );
      setUploadResult({
        created: [],
        duplicates: [],
        errors: [
          {
            filename: "Batch upload",
            message:
              "Choose 1–12 non-empty files, up to 15 MB each and 60 MB in total.",
          },
        ],
      });
      setShowUploads(true);
      if (input.current) input.current.value = "";
      return;
    }
    setUploading(true);
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    form.append("use_ai", String(useAi));
    try {
      const result = await api<UploadResult>("/documents", {
        method: "POST",
        body: form,
      });
      setUploadResult(result);
      setShowUploads(result.errors.length > 0 || result.created.length !== 1);
      await refresh();
      const pieces = [];
      if (result.created.length)
        pieces.push(result.created.length + " bill(s) added to the queue");
      if (result.duplicates.length)
        pieces.push(result.duplicates.length + " duplicate(s) skipped");
      if (result.errors.length)
        pieces.push(
          result.errors
            .map((item) => item.filename + ": " + item.message)
            .join(" · "),
        );
      notify(pieces.join(". "), result.errors.length > 0);
      if (result.created.length === 1) setActiveId(result.created[0].id);
      else if (!result.created.length && result.duplicates.length === 1)
        setActiveId(result.duplicates[0].id);
      setView("invoices");
    } catch (error) {
      setUploadResult({
        created: [],
        duplicates: [],
        errors: [{ filename: "Batch upload", message: message(error) }],
      });
      setShowUploads(true);
      notify(message(error), true);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  const counts = inbox?.counts ?? {
    all: 0,
    review: 0,
    approved: 0,
    processing: 0,
  };
  const exportIds = selected;
  const filtered = documents;
  const queue = reviewQueue.some((doc) => doc.id === activeId)
    ? reviewQueue
    : documents;
  const activeIndex = queue.findIndex((doc) => doc.id === activeId);
  function openBill(id: string) {
    if (
      hasUnsavedChanges &&
      !window.confirm("Leave without saving your changes?")
    )
      return;
    setHasUnsavedChanges(false);
    setView("invoices");
    if (!activeId || !reviewQueue.some((doc) => doc.id === id))
      setReviewQueue(documents);
    setActiveId(id);
    setShowUploads(false);
  }
  function nav(next: View) {
    if (
      hasUnsavedChanges &&
      !window.confirm("Leave without saving your changes?")
    )
      return;
    setHasUnsavedChanges(false);
    setView(next);
    setActiveId(null);
    setReviewQueue([]);
  }
  function openExport(ids: string[]) {
    if (ids.length > 200) {
      notify("Select up to 200 bills per workbook.", true);
      return;
    }
    setExporting(ids);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="/"
          onClick={(event) => {
            event.preventDefault();
            nav("invoices");
          }}
        >
          <span className="brand-mark">
            <LayoutGrid size={24} />
          </span>
          <span>
            <strong>Akshay</strong>
            <small>Store workspace</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          <button
            className={view === "invoices" ? "active" : ""}
            onClick={() => nav("invoices")}
          >
            <Inbox size={18} />
            Invoices <span className="nav-count">{inbox?.total ?? 0}</span>
          </button>
          <button
            className={view === "templates" ? "active" : ""}
            onClick={() => nav("templates")}
          >
            <FileSpreadsheet size={18} />
            Excel templates
          </button>
          <button
            className={view === "exports" ? "active" : ""}
            onClick={() => nav("exports")}
          >
            <ArrowDownToLine size={18} />
            Export history
          </button>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={22} />
          <strong>Review before you export</strong>
          <p>Your original bills stay linked to every entry.</p>
        </div>
        <div className="sidebar-bottom">
          <button className="help-button" onClick={() => setHelp(true)}>
            <CircleHelp size={17} />
            How it works
          </button>
          <div className="local-status">
            <span
              className={"connection-dot " + (connectionError ? "offline" : "")}
            />
            <span>
              Local workspace<small>Saved on this computer</small>
            </span>
            <HardDrive size={15} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>Workspace</span>
          <ChevronRight size={14} />
          <strong>
            {activeId
              ? "Review bill"
              : view === "invoices"
                ? "Invoices"
                : view === "templates"
                  ? "Excel templates"
                  : "Export history"}
          </strong>
          <span className="topbar-right">
            {uploadResult && (
              <button
                className="text-button upload-report-button"
                onClick={() => setShowUploads(true)}
              >
                Last upload
                {uploadResult.errors.length
                  ? ` · ${uploadResult.errors.length} issues`
                  : ""}
              </button>
            )}
            <span className="local-pill">
              <HardDrive size={12} /> Local
            </span>
            <span className="operator-avatar">AK</span>
          </span>
        </header>
        {connectionError && (
          <div className="connection-banner">
            {connectionError}
            <button onClick={() => void refresh()}>Reconnect</button>
          </div>
        )}
        <main>
          {activeId && view === "invoices" ? (
            active ? (
              <Review
                document={active}
                health={health}
                notify={notify}
                onDirty={setHasUnsavedChanges}
                previous={activeIndex > 0 ? queue[activeIndex - 1] : undefined}
                next={activeIndex >= 0 ? queue[activeIndex + 1] : undefined}
                onNavigate={openBill}
                onBack={() => nav("invoices")}
                onChange={(doc) => {
                  setActive(doc);
                  if (doc.status !== "approved")
                    setSelected((current) =>
                      current.filter((id) => id !== doc.id),
                    );
                  void refresh();
                }}
                onExport={() => openExport([active.id])}
              />
            ) : activeError ? (
              <div className="page">
                <div className="panel empty" role="alert">
                  <h3>Could not open this bill</h3>
                  <p>{activeError}</p>
                  <button
                    className="button secondary"
                    onClick={() => nav("invoices")}
                  >
                    Back to invoices
                  </button>
                </div>
              </div>
            ) : (
              <Loading label="Opening bill…" />
            )
          ) : view === "templates" ? (
            <Templates
              templates={templates}
              fields={health?.export_fields || {}}
              defaultFormat={health?.default_format}
              notify={notify}
              onDirty={setHasUnsavedChanges}
              onRefresh={refreshTemplates}
            />
          ) : view === "exports" ? (
            <section className="page">
              <div className="page-heading">
                <div>
                  <span className="eyebrow">YOUR WORKBOOKS</span>
                  <h1>Export history</h1>
                  <p>A record of approved entries, ready to download again.</p>
                </div>
              </div>
              {!exports.length ? (
                <div className="empty panel">
                  <ArrowDownToLine size={34} />
                  <h3>No workbooks yet</h3>
                  <p>
                    Approve your bills, then export them from the invoice
                    workspace.
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => nav("invoices")}
                  >
                    Go to invoices <ArrowRight size={16} />
                  </button>
                </div>
              ) : (
                <div className="panel table-wrap">
                  <table className="documents-table">
                    <thead>
                      <tr>
                        <th>Workbook</th>
                        <th>Created</th>
                        <th>Bills</th>
                        <th>Product rows</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {exports.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <div className="file-cell">
                              <span className="file-icon excel">
                                <FileSpreadsheet size={20} />
                              </span>
                              <span>
                                <strong>Akshay invoices</strong>
                                <small>
                                  {item.id.slice(0, 8)} ·{" "}
                                  {item.template_id
                                    ? "Custom template"
                                    : "Standard workbook"}
                                </small>
                              </span>
                            </div>
                          </td>
                          <td>{day(item.created_at)}</td>
                          <td>{item.documents.length}</td>
                          <td>{item.rows}</td>
                          <td>
                            <a
                              className="button secondary small"
                              href={"/api/exports/" + item.id + "/download"}
                            >
                              <ArrowDownToLine size={15} />
                              Download
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ) : (
            <section className="page">
              <div className="page-heading">
                <div>
                  <span className="eyebrow">SUPPLIER INVOICES</span>
                  <h1>Invoice workspace</h1>
                  <p>Turn your bills into clear, reviewed purchase records.</p>
                </div>
                <div className="button-row">
                  <button
                    className="button secondary"
                    onClick={() => nav("templates")}
                  >
                    <FileSpreadsheet size={16} />
                    Attach template
                  </button>
                  <button
                    className="button primary"
                    onClick={() => input.current?.click()}
                    disabled={uploading}
                  >
                    {uploading ? (
                      <LoaderCircle className="spin" size={17} />
                    ) : (
                      <Plus size={17} />
                    )}
                    Upload bills
                  </button>
                </div>
              </div>
              <div className="stats-grid">
                <div className="stat-card">
                  <span className="stat-icon amber">
                    <FileText size={20} />
                  </span>
                  <div>
                    <span>Awaiting review</span>
                    <strong>{counts.review}</strong>
                    <small>
                      {counts.processing
                        ? counts.processing + " more processing"
                        : "Ready for your attention"}
                    </small>
                  </div>
                </div>
                <div className="stat-card">
                  <span className="stat-icon green">
                    <CheckCheck size={20} />
                  </span>
                  <div>
                    <span>Approved bills</span>
                    <strong>{counts.approved}</strong>
                    <small>Checked and ready to export</small>
                  </div>
                </div>
                <div className="stat-card">
                  <span className="stat-icon blue">
                    <FileCheck2 size={20} />
                  </span>
                  <div>
                    <span>Approved value</span>
                    <strong className="money-stat">
                      {money(inbox?.approved_value)}
                    </strong>
                    <small>
                      {query || dateFrom || dateTo
                        ? "Matching search and bill dates"
                        : "Total of approved invoices"}
                    </small>
                  </div>
                </div>
              </div>
              <div
                className={"dropzone " + (dragging ? "dragging" : "")}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  void upload(event.dataTransfer.files);
                }}
              >
                <div className="drop-icon">
                  {uploading ? (
                    <LoaderCircle className="spin" size={25} />
                  ) : (
                    <Upload size={25} />
                  )}
                </div>
                <div className="drop-copy">
                  <h3>
                    {uploading ? "Adding your bills…" : "Drop your bills here"}
                  </h3>
                  <p>PDF, JPG or PNG · up to 15 MB each · 12 files per batch</p>
                </div>
                <button
                  className="button secondary"
                  onClick={() => input.current?.click()}
                  disabled={uploading}
                >
                  <FolderOpen size={16} />
                  Browse files
                </button>
              </div>
              {health?.ai.available && (
                <label className="ai-option">
                  <input
                    type="checkbox"
                    checked={useAi}
                    onChange={(event) => setUseAi(event.target.checked)}
                  />
                  <Sparkles size={15} />
                  Use local AI assistance <span>{health.ai.model}</span>
                </label>
              )}
              <div className="panel invoice-panel">
                <div className="table-toolbar">
                  <div className="tabs">
                    {[
                      ["all", "All bills", counts.all],
                      ["review", "Needs review", counts.review],
                      ["approved", "Approved", counts.approved],
                      ["processing", "Processing", counts.processing],
                    ].map(([key, label, count]) => (
                      <button
                        key={key}
                        className={filter === key ? "active" : ""}
                        onClick={() => {
                          setFilter(String(key));
                          setPage(1);
                        }}
                      >
                        {label}
                        <span>{count}</span>
                      </button>
                    ))}
                  </div>
                  <label className="search-field">
                    <Search size={15} />
                    <input
                      aria-label="Search bills"
                      placeholder="Bill, supplier, GSTIN…"
                      value={search}
                      maxLength={200}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                </div>
                <div className="inbox-filters">
                  <label className="field">
                    <span>Bill date from</span>
                    <input
                      type="date"
                      value={dateFrom}
                      max={dateTo || undefined}
                      onChange={(event) => {
                        setDateFrom(event.target.value);
                        setPage(1);
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>Bill date to</span>
                    <input
                      type="date"
                      value={dateTo}
                      min={dateFrom || undefined}
                      onChange={(event) => {
                        setDateTo(event.target.value);
                        setPage(1);
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>Sort by</span>
                    <select
                      value={order}
                      onChange={(event) => {
                        setOrder(event.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="newest">Recently uploaded</option>
                      <option value="bill_date">Newest bill date</option>
                      <option value="amount">Highest amount</option>
                    </select>
                  </label>
                  {(search || dateFrom || dateTo || filter !== "all") && (
                    <button
                      className="text-button"
                      onClick={() => {
                        setSearch("");
                        setQuery("");
                        setDateFrom("");
                        setDateTo("");
                        setFilter("all");
                        setPage(1);
                      }}
                    >
                      Clear filters
                    </button>
                  )}
                </div>
                {dateFrom && dateTo && dateFrom > dateTo && (
                  <p className="filter-error" role="alert">
                    Choose an end date on or after the start date.
                  </p>
                )}
                <div className="selection-bar">
                  <span>
                    {exportIds.length
                      ? exportIds.length + " approved bill(s) selected"
                      : "Select approved bills to create a workbook"}
                  </span>
                  {selected.length > 0 && (
                    <button
                      className="text-button"
                      onClick={() => setSelected([])}
                    >
                      Clear selection
                    </button>
                  )}
                  <button
                    className="button secondary small"
                    disabled={!exportIds.length}
                    onClick={() => openExport(exportIds)}
                  >
                    <ArrowDownToLine size={14} />
                    Export selected
                  </button>
                </div>
                {loading ? (
                  <Loading />
                ) : !filtered.length ? (
                  <div className="empty">
                    <span className="empty-illustration">
                      <FileText size={32} />
                      <span>
                        <Plus size={13} />
                      </span>
                    </span>
                    <h3>
                      {inbox?.total
                        ? "No bills match your filters"
                        : "Your first bill starts here"}
                    </h3>
                    <p>
                      {inbox?.total
                        ? "Try another supplier, bill number or status."
                        : "Upload a supplier bill. Review its entries, then export to Excel."}
                    </p>
                    {!inbox?.total && (
                      <button
                        className="button primary"
                        onClick={() => input.current?.click()}
                      >
                        <Plus size={16} />
                        Add your first bill
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table className="documents-table">
                      <thead>
                        <tr>
                          <th className="checkbox-cell">
                            <input
                              type="checkbox"
                              aria-label="Select all visible approved bills"
                              checked={
                                filtered.some(
                                  (doc) => doc.status === "approved",
                                ) &&
                                filtered
                                  .filter((doc) => doc.status === "approved")
                                  .every((doc) => selected.includes(doc.id))
                              }
                              onChange={(event) => {
                                const ids = filtered
                                  .filter((doc) => doc.status === "approved")
                                  .map((doc) => doc.id);
                                setSelected(
                                  event.target.checked
                                    ? [...new Set([...selected, ...ids])].slice(
                                        0,
                                        200,
                                      )
                                    : selected.filter(
                                        (id) => !ids.includes(id),
                                      ),
                                );
                              }}
                            />
                          </th>
                          <th>Document</th>
                          <th>Supplier</th>
                          <th>Bill date</th>
                          <th className="align-right">Total</th>
                          <th>Status</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((doc) => (
                          <tr key={doc.id}>
                            <td className="checkbox-cell">
                              <input
                                type="checkbox"
                                aria-label={"Select " + doc.filename}
                                disabled={
                                  doc.status !== "approved" ||
                                  (selected.length >= 200 &&
                                    !selected.includes(doc.id))
                                }
                                checked={selected.includes(doc.id)}
                                onChange={(event) =>
                                  setSelected(
                                    event.target.checked
                                      ? [...selected, doc.id]
                                      : selected.filter((id) => id !== doc.id),
                                  )
                                }
                              />
                            </td>
                            <td>
                              <button
                                className="file-cell file-link"
                                onClick={() => openBill(doc.id)}
                              >
                                <span
                                  className={
                                    "file-icon " +
                                    (doc.filename.toLowerCase().endsWith(".pdf")
                                      ? "pdf"
                                      : "image")
                                  }
                                >
                                  <FileText size={19} />
                                </span>
                                <span>
                                  <strong>{doc.filename}</strong>
                                  <small>
                                    {doc.invoice.bill_number ||
                                      "Bill details pending"}{" "}
                                    · {doc.page_count} page
                                    {doc.page_count === 1 ? "" : "s"}
                                  </small>
                                </span>
                              </button>
                            </td>
                            <td>
                              <span className="supplier-name">
                                {doc.invoice.supplier_name ||
                                  "Not identified yet"}
                              </span>
                            </td>
                            <td className="muted nowrap">
                              {day(doc.invoice.bill_date)}
                            </td>
                            <td className="align-right amount">
                              {money(
                                doc.invoice.grand_total,
                                doc.invoice.currency,
                              )}
                            </td>
                            <td>
                              <Status status={doc.status} />
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={"Review " + doc.filename}
                                onClick={() => openBill(doc.id)}
                              >
                                <ChevronRight size={18} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="table-footer">
                  <span>
                    {inbox?.matched
                      ? `${(inbox.page - 1) * inbox.page_size + 1}–${(inbox.page - 1) * inbox.page_size + filtered.length}`
                      : "0"}{" "}
                    of {inbox?.matched ?? 0} matching bills
                  </span>
                  <div className="pagination">
                    <button
                      className="icon-button"
                      aria-label="Previous page of bills"
                      disabled={loading || page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      <ChevronLeft size={17} />
                    </button>
                    <span>
                      Page {inbox?.page ?? page} of{" "}
                      {Math.max(1, Math.ceil((inbox?.matched ?? 0) / 25))}
                    </span>
                    <button
                      className="icon-button"
                      aria-label="Next page of bills"
                      disabled={loading || page * 25 >= (inbox?.matched ?? 0)}
                      onClick={() => setPage(page + 1)}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                </div>
              </div>
              <div className="workflow-strip">
                <span>
                  <span>1</span>Upload bills
                </span>
                <ChevronRight size={14} />
                <span>
                  <span>2</span>Review entries
                </span>
                <ChevronRight size={14} />
                <span>
                  <span>3</span>Approve & export
                </span>
              </div>
            </section>
          )}
        </main>
      </div>
      <input
        hidden
        ref={input}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg"
        onChange={(event) =>
          event.target.files && void upload(event.target.files)
        }
      />
      {toast && (
        <div className={"toast " + (toast.error ? "error" : "")} role="status">
          {toast.error ? <CircleHelp size={18} /> : <Check size={18} />}
          <span>{toast.text}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {help && (
        <Modal
          title="A clear path from bill to workbook"
          onClose={() => setHelp(false)}
        >
          <div className="modal-body help-content">
            <div>
              <span>1</span>
              <section>
                <h3>Upload your bills</h3>
                <p>
                  Add PDF, JPG or PNG files. Text extraction or local OCR
                  prepares a draft.
                </p>
              </section>
            </div>
            <div>
              <span>2</span>
              <section>
                <h3>Review against the original</h3>
                <p>
                  Check supplier details, each product row and the totals.
                  Correct missing or uncertain entries.
                </p>
              </section>
            </div>
            <div>
              <span>3</span>
              <section>
                <h3>Approve and export</h3>
                <p>
                  Create a standard workbook, or map your own Excel template.
                  Only approved bills are included.
                </p>
              </section>
            </div>
            <p className="info-note">
              This workspace runs on your computer. Optional local AI{" "}
              {health?.ai.available
                ? "is available: " + health.ai.model
                : "is not configured"}
              . Shared staff access and POS integration are not enabled in this
              version.
            </p>
          </div>
        </Modal>
      )}
      {showUploads && uploadResult && (
        <UploadReport
          result={uploadResult}
          onClose={() => setShowUploads(false)}
          onOpen={openBill}
        />
      )}
      {exporting && (
        <ExportDialog
          ids={exporting}
          templates={templates}
          notify={notify}
          onClose={() => setExporting(null)}
          onDone={() => {
            void refreshExports();
          }}
        />
      )}
    </div>
  );
}

function ExportDialog({
  ids,
  templates,
  notify,
  onClose,
  onDone,
}: {
  ids: string[];
  templates: Template[];
  notify: (text: string, error?: boolean) => void;
  onClose: () => void;
  onDone: () => void;
}) {
  const [template, setTemplate] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    id: string;
    row_count: number;
    bill_count: number;
  } | null>(null);
  async function create() {
    setBusy(true);
    try {
      setResult(
        await api("/exports", {
          method: "POST",
          body: JSON.stringify({
            document_ids: ids,
            template_id: template || null,
          }),
        }),
      );
      onDone();
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={result ? "Your workbook is ready" : "Create an Excel workbook"}
      onClose={busy ? () => {} : onClose}
    >
      <div className="modal-body">
        {result ? (
          <div className="export-success">
            <span>
              <CheckCheck size={30} />
            </span>
            <h3>
              {result.row_count} product rows, {result.bill_count} bill(s)
            </h3>
            <p>
              Created from approved entries. Your original documents are
              unchanged.
            </p>
            <a
              className="button primary"
              href={"/api/exports/" + result.id + "/download"}
            >
              <ArrowDownToLine size={16} />
              Download workbook
            </a>
          </div>
        ) : (
          <>
            <p className="muted">
              Export {ids.length} approved bill(s) into a new .xlsx file.
            </p>
            <label className="field">
              <span>Workbook format</span>
              <select
                value={template}
                onChange={(event) => setTemplate(event.target.value)}
              >
                <option value="">
                  Default format (fixed) · Line Items + Bill Summary
                </option>
                {templates
                  .filter(
                    (item) =>
                      item.config.mapping &&
                      Object.keys(item.config.mapping).length,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.filename}
                    </option>
                  ))}
              </select>
            </label>
            <div className="info-note">
              <FileSpreadsheet size={18} />
              <span>
                {template
                  ? "Data is written only to your mapped empty cells. Existing values and formula cells will not be overwritten."
                  : "One row per product, plus a separate bill summary with taxes, totals and source filenames."}
              </span>
            </div>
          </>
        )}
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose} disabled={busy}>
          {result ? "Done" : "Cancel"}
        </button>
        {!result && (
          <button
            className="button primary"
            onClick={() => void create()}
            disabled={busy}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <FileSpreadsheet size={16} />
            )}
            {busy ? "Creating…" : "Create workbook"}
          </button>
        )}
      </footer>
    </Modal>
  );
}
