import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  CheckCheck,
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
import type { Document, ExportRecord, Health, Template } from "./types";

type View = "invoices" | "templates" | "exports";
export default function App() {
  const [view, setView] = useState<View>("invoices");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [useAi, setUseAi] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<Document | null>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
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
    try {
      const docs = await api<Document[]>("/documents");
      setDocuments(docs);
      setConnectionError("");
    } catch (error) {
      setConnectionError(message(error));
    } finally {
      setLoading(false);
    }
  }, []);
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
    void refresh();
    void refreshTemplates();
    void refreshExports();
    void api<Health>("/health")
      .then(setHealth)
      .catch(() => {});
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
    return () => clearInterval(timer);
  }, [refresh, refreshTemplates, refreshExports]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    setActive(null);
    if (!activeId) return;
    let canceled = false;
    void api<Document>("/documents/" + activeId)
      .then((doc) => {
        if (!canceled) setActive(doc);
      })
      .catch((error) => {
        if (!canceled) notify(message(error), true);
      });
    return () => {
      canceled = true;
    };
  }, [activeId, notify]);

  async function upload(files: FileList | File[]) {
    if (!files.length || uploading) return;
    setUploading(true);
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    form.append("use_ai", String(useAi));
    try {
      const result = await api<{
        created: { id: string; filename: string }[];
        duplicates: { id: string; filename: string }[];
        errors: { filename: string; message: string }[];
      }>("/documents", { method: "POST", body: form });
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
      notify(message(error), true);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  const pending = documents.filter(
    (doc) => doc.status === "needs_review" || doc.status === "failed",
  );
  const approved = documents.filter((doc) => doc.status === "approved");
  const processing = documents.filter((doc) =>
    ["queued", "processing"].includes(doc.status),
  );
  const approvedIds = new Set(approved.map((doc) => doc.id));
  const exportIds = selected.filter((id) => approvedIds.has(id));
  const filtered = documents.filter((doc) => {
    const matches =
      filter === "all" ||
      (filter === "review" && pending.includes(doc)) ||
      (filter === "approved" && doc.status === "approved") ||
      (filter === "processing" &&
        ["queued", "processing"].includes(doc.status));
    return (
      matches &&
      (
        doc.filename +
        " " +
        doc.invoice.supplier_name +
        " " +
        doc.invoice.bill_number
      )
        .toLowerCase()
        .includes(search.toLowerCase())
    );
  });
  function nav(next: View) {
    setView(next);
    setActiveId(null);
  }
  function openExport(ids: string[]) {
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
            Invoices <span className="nav-count">{documents.length}</span>
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
            <span className="local-pill">
              <HardDrive size={12} /> Local
            </span>
            <span className="operator-avatar">AK</span>
          </span>
        </header>
        {connectionError && (
          <div className="connection-banner">
            The backend is not connected. Start the local server on port 8001.
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
                onBack={() => setActiveId(null)}
                onChange={(doc) => {
                  setActive(doc);
                  void refresh();
                }}
                onExport={() => openExport([active.id])}
              />
            ) : (
              <Loading label="Opening bill…" />
            )
          ) : view === "templates" ? (
            <Templates
              templates={templates}
              fields={health?.export_fields || {}}
              notify={notify}
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
                    <strong>{pending.length}</strong>
                    <small>
                      {processing.length
                        ? processing.length + " more processing"
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
                    <strong>{approved.length}</strong>
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
                      {money(
                        approved.reduce(
                          (sum, doc) =>
                            sum + Number(doc.invoice.grand_total || 0),
                          0,
                        ),
                      )}
                    </strong>
                    <small>Total of approved invoices</small>
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
                      ["all", "All bills", documents.length],
                      ["review", "Needs review", pending.length],
                      ["approved", "Approved", approved.length],
                      ["processing", "Processing", processing.length],
                    ].map(([key, label, count]) => (
                      <button
                        key={key}
                        className={filter === key ? "active" : ""}
                        onClick={() => setFilter(String(key))}
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
                      placeholder="Search bills or suppliers…"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                </div>
                <div className="selection-bar">
                  <span>
                    {exportIds.length
                      ? exportIds.length + " approved bill(s) selected"
                      : "Select approved bills to create a workbook"}
                  </span>
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
                      {documents.length
                        ? "No bills match your filters"
                        : "Your first bill starts here"}
                    </h3>
                    <p>
                      {documents.length
                        ? "Try another supplier, bill number or status."
                        : "Upload a supplier bill. Review its entries, then export to Excel."}
                    </p>
                    {!documents.length && (
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
                                    ? [...new Set([...selected, ...ids])]
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
                                disabled={doc.status !== "approved"}
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
                                onClick={() => setActiveId(doc.id)}
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
                              {money(doc.invoice.grand_total)}
                            </td>
                            <td>
                              <Status status={doc.status} />
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={"Review " + doc.filename}
                                onClick={() => setActiveId(doc.id)}
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
                    {filtered.length} of {documents.length} bills
                  </span>
                  <span>
                    <ShieldCheck size={13} />
                    Originals preserved · Approval required
                  </span>
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
                <option value="">Standard · Line Items + Bill Summary</option>
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
