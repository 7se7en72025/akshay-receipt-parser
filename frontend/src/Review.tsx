import { useEffect, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeft,
  CheckCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  LoaderCircle,
  Plus,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { api, day, message, moment, money } from "./api";
import { History } from "./History";
import { Verification } from "./Verification";
import { useUnsavedChanges } from "./useUnsavedChanges";
import { Status } from "./components";
import {
  emptyItem,
  type Document,
  type Health,
  type Invoice,
  type Item,
  type Notify,
} from "./types";

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  wide = false,
}: {
  label: string;
  value: string | number | null;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  wide?: boolean;
}) {
  return (
    <label className={"field " + (wide ? "wide" : "")}>
      <span>{label}</span>
      <input
        type={type}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder || "Not recorded"}
        step={type === "number" ? "any" : undefined}
      />
    </label>
  );
}

export function Review({
  document: doc,
  health,
  notify,
  onBack,
  onChange,
  onExport,
  onDirty,
  previous,
  next,
  onNavigate,
}: {
  document: Document;
  health: Health | null;
  notify: Notify;
  onBack: () => void;
  onChange: (doc: Document) => void;
  onExport: () => void;
  onDirty: (dirty: boolean) => void;
  previous?: { id: string; filename: string };
  next?: { id: string; filename: string };
  onNavigate: (id: string) => void;
}) {
  const [invoice, setInvoice] = useState<Invoice>(structuredClone(doc.invoice));
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState("details");
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [previewError, setPreviewError] = useState(false);
  const [busy, setBusy] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [historyId, setHistoryId] = useState<string | null>(null);
  const [focusRow, setFocusRow] = useState<number | null>(null);
  useUnsavedChanges(dirty, onDirty);
  useEffect(() => {
    if (tab !== "items" || focusRow === null) return;
    const row = window.document.getElementById("product-row-" + focusRow);
    row?.scrollIntoView({ block: "center" });
    row
      ?.querySelector<HTMLInputElement>("input")
      ?.focus({ preventScroll: true });
    setFocusRow(null);
  }, [tab, focusRow]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (dirty && !busy && !approved && !processing) void save();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  });
  const approved = doc.status === "approved";
  const processing = doc.status === "queued" || doc.status === "processing";
  useEffect(() => {
    setInvoice(structuredClone(doc.invoice));
    setDirty(false);
    setAcknowledged(false);
  }, [doc.id, doc.version, doc.invoice]);
  useEffect(() => {
    setPreviewError(false);
  }, [doc.id, page]);
  function setField(key: keyof Invoice, value: string) {
    const textFields = [
      "supplier_name",
      "supplier_gstin",
      "bill_number",
      "purchase_number",
      "notes",
    ];
    setInvoice((current) => ({
      ...current,
      [key]: value === "" && !textFields.includes(key) ? null : value,
    }));
    setDirty(true);
  }
  function setItem(index: number, key: keyof Item, value: string) {
    const textFields = ["description", "hsn", "unit"];
    setInvoice((current) => ({
      ...current,
      items: current.items.map((item, position) =>
        position !== index
          ? item
          : {
              ...item,
              [key]:
                key === "source_page"
                  ? Number(value)
                  : value === "" && !textFields.includes(key)
                    ? null
                    : value,
            },
      ),
    }));
    setDirty(true);
  }
  async function save(approve = false) {
    setBusy(approve ? "approve" : "save");
    try {
      const result = await api<Document>(
        "/documents/" + doc.id + (approve ? "/approve" : ""),
        {
          method: approve ? "POST" : "PUT",
          body: JSON.stringify({
            invoice,
            version: doc.version,
            ...(approve
              ? { acknowledge_warnings: acknowledged, review_note: reviewNote }
              : {}),
          }),
        },
      );
      onChange(result);
      notify(
        approve
          ? "Bill approved. It is ready for Excel export."
          : "Draft saved. Validation checks updated.",
      );
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy("");
    }
  }
  async function retry(useAi: boolean) {
    if (
      !window.confirm(
        "Re-extract this bill? The saved draft will be replaced. Its previous version is retained in review history.",
      )
    )
      return;
    setBusy("retry");
    try {
      const result = await api<Document>("/documents/" + doc.id + "/retry", {
        method: "POST",
        body: JSON.stringify({ version: doc.version, use_ai: useAi }),
      });
      onChange(result);
      notify("Bill added to the processing queue.");
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="page review-page">
      <div className="review-navigation">
        <button className="back-link" onClick={onBack}>
          <ArrowLeft size={15} />
          All invoices
        </button>
        <div className="button-row">
          <button
            className="button secondary small"
            disabled={!previous || !!busy}
            title={previous?.filename}
            onClick={() => previous && onNavigate(previous.id)}
          >
            <ChevronLeft size={15} />
            Previous bill
          </button>
          <button
            className="button secondary small"
            disabled={!next || !!busy}
            title={next?.filename}
            onClick={() => next && onNavigate(next.id)}
          >
            Next bill
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
      <div className="page-heading">
        <div>
          <div className="review-title">
            <h1>
              {invoice.bill_number
                ? "Bill " + invoice.bill_number
                : "Review bill"}
            </h1>
            <Status status={doc.status} />
          </div>
          <p>
            {doc.filename} <span className="separator">·</span>{" "}
            {doc.method
              ? doc.method.replaceAll("+", " + ").toUpperCase()
              : "Preparing extraction"}{" "}
            {dirty && <span className="unsaved">Unsaved changes</span>}
          </p>
        </div>
        <div className="button-row">
          {!processing && (
            <button
              className="button secondary"
              disabled={!!busy}
              onClick={async () => {
                if (
                  dirty &&
                  !window.confirm(
                    "Reload the saved record and discard unsaved edits?",
                  )
                )
                  return;
                setBusy("reload");
                try {
                  onChange(await api<Document>("/documents/" + doc.id));
                } catch (error) {
                  notify(message(error), true);
                } finally {
                  setBusy("");
                }
              }}
            >
              <RotateCcw size={15} />
              Reload saved
            </button>
          )}
          {approved ? (
            <>
              <button
                className="button secondary"
                onClick={() => void save()}
                disabled={!!busy}
              >
                <RotateCcw size={15} />
                Reopen draft
              </button>
              <button className="button primary" onClick={onExport}>
                <ArrowDownToLine size={16} />
                Export bill
              </button>
            </>
          ) : (
            <>
              <button
                className="button secondary"
                onClick={() => void save()}
                disabled={!!busy || processing}
              >
                {busy === "save" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Save size={16} />
                )}
                Save draft
              </button>
              <button
                className="button primary"
                onClick={() => void save(true)}
                disabled={
                  !!busy ||
                  processing ||
                  dirty ||
                  !doc.validation.can_approve ||
                  (doc.validation.warnings > 0 && !acknowledged)
                }
                title={
                  dirty
                    ? "Save your changes before approval"
                    : doc.validation.errors
                      ? "Resolve the validation errors first"
                      : "Approve reviewed entries"
                }
              >
                {busy === "approve" ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <CheckCheck size={17} />
                )}
                Approve bill
              </button>
            </>
          )}
        </div>
      </div>
      {!processing && invoice.currency !== "INR" && (
        <div className="notice error-note">
          <AlertTriangle size={21} />
          <div>
            <strong>Foreign-currency source · Review only</strong>
            <p>
              This bill is in {invoice.currency}. Approval and INR export are
              blocked. The source currency cannot be relabelled as INR.
            </p>
          </div>
        </div>
      )}
      {processing && (
        <div className="notice processing-note">
          <LoaderCircle size={20} className="spin" />
          <div>
            <strong>
              {doc.status === "queued"
                ? "Waiting for the processing worker"
                : "Reading your bill"}
            </strong>
            <p>
              The original is saved. This page updates automatically when the
              review draft is ready.
            </p>
          </div>
        </div>
      )}
      {doc.error && (
        <div className="notice error-note">
          <AlertCircle size={21} />
          <div>
            <strong>Automatic extraction needs attention</strong>
            <p>{doc.error}</p>
            <button
              className="text-button"
              onClick={() => void retry(false)}
              disabled={!!busy}
            >
              Retry extraction
            </button>
            <span className="muted">
              {" "}
              or enter the bill details manually below.
            </span>
          </div>
        </div>
      )}
      {approved && (
        <div className="notice success-note">
          <ShieldCheck size={20} />
          <div>
            <strong>Approved and ready to export</strong>
            <p>
              Reopen the draft to make corrections. It will need approval again
              before the next export.
            </p>
          </div>
        </div>
      )}
      <div className="review-summary">
        <span>
          <FileText size={15} />
          {invoice.items.length} product rows
        </span>
        <span>
          Bill date <strong>{day(invoice.bill_date)}</strong>
        </span>
        <span>
          Grand total{" "}
          <strong>{money(invoice.grand_total, invoice.currency)}</strong>
        </span>
        <button
          onClick={() => setTab("checks")}
          className={doc.validation.errors ? "text-danger" : ""}
        >
          {doc.validation.errors ? (
            <AlertCircle size={14} />
          ) : (
            <ShieldCheck size={14} />
          )}
          {doc.validation.errors} errors · {doc.validation.warnings} warnings
        </button>
      </div>
      <div className="review-grid">
        <div className="panel source-panel">
          <div className="panel-heading">
            <div>
              <FileText size={16} />
              <strong>Original document</strong>
            </div>
            <a
              href={"/api/documents/" + doc.id + "/source"}
              className="icon-button"
              aria-label="Download original bill"
            >
              <ArrowDownToLine size={16} />
            </a>
          </div>
          <div className="preview-toolbar">
            <div>
              <button
                className="icon-button"
                aria-label="Previous page"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              <span>
                {page} / {doc.page_count}
              </span>
              <button
                className="icon-button"
                aria-label="Next page"
                disabled={page >= doc.page_count}
                onClick={() => setPage(page + 1)}
              >
                <ChevronRight size={15} />
              </button>
            </div>
            <div>
              <button
                className="icon-button"
                aria-label="Zoom out"
                disabled={zoom <= 75}
                onClick={() => setZoom(zoom - 25)}
              >
                <ZoomOut size={15} />
              </button>
              <span>{zoom}%</span>
              <button
                className="icon-button"
                aria-label="Zoom in"
                disabled={zoom >= 250}
                onClick={() => setZoom(zoom + 25)}
              >
                <ZoomIn size={15} />
              </button>
            </div>
          </div>
          <div className="preview-viewport">
            {previewError ? (
              <div className="empty">
                <FileText size={30} />
                <h3>Preview unavailable</h3>
                <p>Download the original to review this bill.</p>
              </div>
            ) : (
              <img
                style={{ width: zoom + "%" }}
                src={"/api/documents/" + doc.id + "/preview/" + page}
                alt={"Original bill, page " + page}
                onError={() => setPreviewError(true)}
              />
            )}
          </div>
          <div className="source-footer">
            <ShieldCheck size={13} />
            Original file preserved
          </div>
        </div>
        <div className="panel editor-panel">
          <div className="editor-tabs">
            {[
              ["details", "Bill details"],
              ["items", "Line items (" + invoice.items.length + ")"],
              ["checks", "Checks & history"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="editor-content">
            {tab === "details" && (
              <fieldset
                disabled={approved || processing || !!busy}
                className="editor-fieldset"
              >
                <div className="section-title">
                  <h3>Supplier & bill</h3>
                  <span>{invoice.currency} · Source currency</span>
                </div>
                <div className="form-grid">
                  <Field
                    label="Supplier name"
                    value={invoice.supplier_name}
                    onChange={(value) => setField("supplier_name", value)}
                    wide
                  />
                  <Field
                    label="Supplier GSTIN"
                    value={invoice.supplier_gstin}
                    onChange={(value) => setField("supplier_gstin", value)}
                  />
                  <Field
                    label="Bill number"
                    value={invoice.bill_number}
                    onChange={(value) => setField("bill_number", value)}
                  />
                  <Field
                    label="Bill date"
                    value={invoice.bill_date}
                    type="date"
                    onChange={(value) => setField("bill_date", value)}
                  />
                  <Field
                    label="Purchase number"
                    value={invoice.purchase_number}
                    onChange={(value) => setField("purchase_number", value)}
                  />
                </div>
                <div className="section-title spaced">
                  <h3>Bill totals</h3>
                  <span>As printed on the bill</span>
                </div>
                {invoice.secondary_currency && (
                  <p className="info-note">
                    Original subtotal:{" "}
                    {money(
                      invoice.secondary_subtotal,
                      invoice.secondary_currency,
                    )}{" "}
                    · Printed exchange rate: {invoice.exchange_rate}. Printed
                    source entries remain unchanged.
                  </p>
                )}
                {invoice.amounts_include_tax && (
                  <p className="info-note">
                    Item amounts include tax. The taxable subtotal is shown
                    separately; printed item amounts are preserved.
                  </p>
                )}
                <div className="form-grid">
                  {[
                    ["taxable_total", "Taxable total"],
                    ["cgst_total", "CGST total"],
                    ["sgst_total", "SGST / UTGST total"],
                    ["igst_total", "IGST total"],
                    ["cess_total", "Cess total"],
                    ["round_off", "Round off"],
                    ["grand_total", "Grand total"],
                    ["other_tax_total", "Other tax / VAT"],
                    ["charges_total", "Shipping & other charges"],
                    ["discount_total", "Bill discount"],
                    ["withholding_total", "Withholding tax"],
                  ].map(([key, label]) => (
                    <Field
                      key={key}
                      label={label + " (" + invoice.currency + ")"}
                      type="number"
                      value={invoice[key as keyof Invoice] as string | null}
                      onChange={(value) =>
                        setField(key as keyof Invoice, value)
                      }
                    />
                  ))}
                </div>
                <label className="field spaced">
                  <span>Notes</span>
                  <textarea
                    rows={3}
                    value={invoice.notes}
                    onChange={(event) => setField("notes", event.target.value)}
                    placeholder="Any context to keep with this purchase record…"
                  />
                </label>
              </fieldset>
            )}
            {tab === "items" && (
              <div>
                <p className="section-description">
                  Check each product against the original. Blank amounts are
                  unknown, not automatically zero.
                </p>
                {invoice.items.map((item, index) => (
                  <fieldset
                    key={index}
                    id={"product-row-" + index}
                    disabled={approved || processing || !!busy}
                    className="item-card"
                  >
                    <div className="item-heading">
                      <span className="item-number">{index + 1}</span>
                      <strong>{item.description || "New product"}</strong>
                      <button
                        className="icon-button danger"
                        aria-label={"Remove item " + (index + 1)}
                        onClick={() => {
                          setInvoice((current) => ({
                            ...current,
                            items: current.items.filter((_, i) => i !== index),
                          }));
                          setDirty(true);
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                    <div className="form-grid">
                      <Field
                        label="Product description"
                        value={item.description}
                        onChange={(value) =>
                          setItem(index, "description", value)
                        }
                        wide
                      />
                      <Field
                        label="HSN"
                        value={item.hsn}
                        onChange={(value) => setItem(index, "hsn", value)}
                      />
                      <Field
                        label="Source page"
                        value={item.source_page}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "source_page", value)
                        }
                      />
                      <Field
                        label="Quantity"
                        value={item.quantity}
                        type="number"
                        onChange={(value) => setItem(index, "quantity", value)}
                      />
                      <Field
                        label="Unit"
                        value={item.unit}
                        onChange={(value) => setItem(index, "unit", value)}
                      />
                      <Field
                        label={
                          "Rate (" +
                          (invoice.secondary_currency || invoice.currency) +
                          ")"
                        }
                        value={item.unit_price}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "unit_price", value)
                        }
                      />
                      <Field
                        label={
                          invoice.amounts_include_tax
                            ? "Printed amount including tax"
                            : "Printed item amount (" +
                              (item.secondary_currency
                                ? invoice.currency
                                : invoice.secondary_currency ||
                                  invoice.currency) +
                              ")"
                        }
                        value={item.taxable_amount}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "taxable_amount", value)
                        }
                      />
                      <Field
                        label={"CGST amount (" + invoice.currency + ")"}
                        value={item.cgst_amount}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "cgst_amount", value)
                        }
                      />
                      <Field
                        label={"SGST amount (" + invoice.currency + ")"}
                        value={item.sgst_amount}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "sgst_amount", value)
                        }
                      />
                      <Field
                        label={"IGST amount (" + invoice.currency + ")"}
                        value={item.igst_amount}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "igst_amount", value)
                        }
                      />
                      <Field
                        label={"Cess amount (" + invoice.currency + ")"}
                        value={item.cess_amount}
                        type="number"
                        onChange={(value) =>
                          setItem(index, "cess_amount", value)
                        }
                      />
                    </div>
                    <details className="item-advanced">
                      <summary>Tax rates & printed discounts</summary>
                      <p>
                        Discount 1 and 2 preserve the printed columns. Confirm
                        their meaning before approval.
                      </p>
                      {item.secondary_currency && (
                        <p>
                          Original printed amount:{" "}
                          {money(
                            item.secondary_amount,
                            item.secondary_currency,
                          )}
                        </p>
                      )}
                      <div className="form-grid">
                        {[
                          ["cgst_rate", "CGST %"],
                          ["sgst_rate", "SGST %"],
                          ["igst_rate", "IGST %"],
                          ["discount_1", "Discount 1"],
                          ["discount_2", "Discount 2"],
                        ].map(([key, label]) => (
                          <Field
                            key={key}
                            label={label}
                            type="number"
                            value={item[key as keyof Item] as string | null}
                            onChange={(value) =>
                              setItem(index, key as keyof Item, value)
                            }
                          />
                        ))}
                      </div>
                    </details>
                  </fieldset>
                ))}
                {!approved && !processing && (
                  <button
                    className="button secondary full-width"
                    disabled={!!busy || invoice.items.length >= 1500}
                    onClick={() => {
                      setInvoice((current) => ({
                        ...current,
                        items: [...current.items, emptyItem()],
                      }));
                      setDirty(true);
                    }}
                  >
                    <Plus size={16} />
                    Add product row
                  </button>
                )}
              </div>
            )}
            {tab === "checks" && (
              <div className="checks-content">
                <Verification
                  doc={doc}
                  dirty={dirty}
                  notify={notify}
                  onChange={onChange}
                  onPage={setPage}
                />
                {dirty && (
                  <div className="info-note">
                    Checks reflect the last saved version. Save your changes to
                    update them.
                  </div>
                )}
                <div className="section-title">
                  <h3>Validation</h3>
                  <span>
                    {doc.validation.errors} errors · {doc.validation.warnings}{" "}
                    warnings
                  </span>
                </div>
                {!doc.validation.issues.length && (
                  <div className="check-success">
                    <CheckCircle2 size={21} />
                    <span>
                      Recorded values reconcile. Review the source before
                      approval.
                    </span>
                  </div>
                )}
                {doc.validation.issues.map((issue, index) => (
                  <div key={index} className={"check-item " + issue.level}>
                    {issue.level === "error" ? (
                      <AlertCircle size={17} />
                    ) : (
                      <AlertTriangle size={17} />
                    )}
                    <div>
                      <strong>
                        {issue.level === "error"
                          ? "Correction needed"
                          : "Review required"}
                      </strong>
                      <p>{issue.message}</p>
                      {issue.row !== null && (
                        <button
                          className="text-button"
                          onClick={() => {
                            setTab("items");
                            setFocusRow(issue.row);
                          }}
                        >
                          Review item {issue.row + 1}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {doc.extraction_notes.length > 0 && (
                  <>
                    <h3 className="spaced">Extraction notes</h3>
                    {doc.extraction_notes.map((note, index) => (
                      <p className="extraction-note" key={index}>
                        {note}
                      </p>
                    ))}
                  </>
                )}
                {!approved && !processing && (
                  <div className="approval-box">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={acknowledged}
                        onChange={(event) =>
                          setAcknowledged(event.target.checked)
                        }
                      />
                      <span>
                        I have checked the entries against the original and
                        reviewed the warnings.
                      </span>
                    </label>
                    <label className="field">
                      <span>Review note (optional)</span>
                      <textarea
                        value={reviewNote}
                        rows={2}
                        onChange={(event) => setReviewNote(event.target.value)}
                        placeholder="Record any clarification or exception…"
                      />
                    </label>
                  </div>
                )}
                <h3 className="spaced">Activity</h3>
                <div className="activity-list">
                  {doc.history?.map((event) => (
                    <div key={event.id}>
                      <Clock3 size={13} />
                      <button
                        className="text-button"
                        onClick={() => setHistoryId(event.id)}
                      >
                        {(
                          {
                            uploaded: "Original uploaded",
                            extracted: "Draft extracted",
                            saved: "Draft saved",
                            approved: "Bill approved",
                            exported: "Excel exported",
                            requeued: "Re-extraction requested",
                            restored: "Saved version restored",
                          } as Record<string, string>
                        )[event.action] || event.action}
                      </button>
                      <time>{moment(event.created_at)}</time>
                    </div>
                  ))}
                </div>
                <details className="raw-text">
                  <summary>View extracted source text</summary>
                  <pre>
                    {doc.raw_text || "No readable text is available yet."}
                  </pre>
                </details>
              </div>
            )}
          </div>
          <div className="editor-footer">
            <span>
              {dirty
                ? "Save to update checks"
                : approved
                  ? "Approved record"
                  : "Draft saved locally"}
            </span>
            {!approved && !processing && (
              <button
                className="text-button"
                disabled={!health?.ai.available || !!busy || dirty}
                title={
                  health?.ai.available
                    ? "Re-extract the source and let local AI fill missing fields; existing source values are preserved"
                    : "Optional local AI is not configured"
                }
                onClick={() => void retry(true)}
              >
                <Sparkles size={13} />
                Local AI assist
              </button>
            )}
            {!processing && (
              <button className="text-button" onClick={() => setTab("checks")}>
                <Sparkles size={13} /> Verify with AI
              </button>
            )}
          </div>
        </div>
      </div>
      {!approved && !processing && (
        <div className="review-bottom-hint">
          <ShieldCheck size={15} />
          <span>
            {dirty
              ? "Save your draft before approving."
              : doc.validation.errors
                ? "Resolve errors, save, then review the remaining warnings."
                : doc.validation.warnings && !acknowledged
                  ? "Open Checks & history to confirm you reviewed the warnings."
                  : "Review complete? Approve this bill to include it in an export."}
          </span>
          <button className="text-button" onClick={() => setTab("checks")}>
            View checks <ChevronRight size={14} />
          </button>
        </div>
      )}
      {historyId && (
        <History
          doc={doc}
          eventId={historyId}
          onClose={() => setHistoryId(null)}
          notify={notify}
          onRestore={onChange}
          dirty={dirty}
        />
      )}
    </section>
  );
}
