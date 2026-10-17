import { useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { api, day, message, moment, money } from "./api";
import { Loading, Modal } from "./components";
import type { Document, HistoryRecord, Notify } from "./types";

export function History({
  doc,
  eventId,
  onClose,
  onRestore,
  notify,
  dirty,
}: {
  doc: Document;
  eventId: string;
  onClose: () => void;
  onRestore: (doc: Document) => void;
  notify: Notify;
  dirty: boolean;
}) {
  const [record, setRecord] = useState<HistoryRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let canceled = false;
    setRecord(null);
    setError("");
    void api<HistoryRecord>(`/documents/${doc.id}/history/${eventId}`)
      .then((result) => {
        if (!canceled) setRecord(result);
      })
      .catch((error) => {
        if (!canceled) setError(message(error));
      });
    return () => {
      canceled = true;
    };
  }, [doc.id, eventId]);
  async function restore() {
    if (
      !window.confirm(
        "Restore these entries as a new draft? Current entries remain in history. The restored bill will need approval again.",
      )
    )
      return;
    setBusy(true);
    try {
      const result = await api<Document>(
        `/documents/${doc.id}/history/${eventId}/restore`,
        {
          method: "POST",
          body: JSON.stringify({ version: doc.version }),
        },
      );
      onRestore(result);
      notify(
        "Saved version restored as a new draft. Review it before approval.",
      );
      onClose();
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy(false);
    }
  }
  const invoice = record?.invoice;
  return (
    <Modal title="Saved activity" onClose={busy ? () => {} : onClose}>
      <div className="modal-body history-body">
        {error ? (
          <p role="alert" className="text-danger">
            {error}
          </p>
        ) : !record ? (
          <Loading />
        ) : (
          <>
            {dirty && (
              <p className="info-note">
                Save or reload your current edits before restoring a version.
              </p>
            )}
            <p className="muted">
              {record.action} · {moment(record.created_at)}
            </p>
            {record.detail.review_note && (
              <div className="info-note">{record.detail.review_note}</div>
            )}
            {invoice ? (
              <>
                <dl className="snapshot-details">
                  <div>
                    <dt>Supplier</dt>
                    <dd>{invoice.supplier_name || "Not recorded"}</dd>
                  </div>
                  <div>
                    <dt>Bill</dt>
                    <dd>
                      {invoice.bill_number || "Not recorded"} ·{" "}
                      {day(invoice.bill_date)}
                    </dd>
                  </div>
                  <div>
                    <dt>Taxable total</dt>
                    <dd>{money(invoice.taxable_total)}</dd>
                  </div>
                  <div>
                    <dt>Grand total</dt>
                    <dd>{money(invoice.grand_total)}</dd>
                  </div>
                </dl>
                <div className="table-wrap">
                  <table className="mapping-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Quantity</th>
                        <th>Taxable</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoice.items.map((item, index) => (
                        <tr key={index}>
                          <td>{item.description || "Unnamed product"}</td>
                          <td>
                            {item.quantity ?? "—"} {item.unit}
                          </td>
                          <td>{money(item.taxable_amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details className="raw-text">
                  <summary>View complete saved record</summary>
                  <pre>{JSON.stringify(invoice, null, 2)}</pre>
                </details>
              </>
            ) : (
              <p>
                This activity has no invoice snapshot. It records an upload,
                extraction count or export.
              </p>
            )}
          </>
        )}
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose} disabled={busy}>
          Close
        </button>
        {invoice && (
          <button
            className="button primary"
            onClick={() => void restore()}
            disabled={
              dirty || busy || ["queued", "processing"].includes(doc.status)
            }
          >
            <RotateCcw size={15} />
            {busy ? "Restoring…" : "Restore as draft"}
          </button>
        )}
      </footer>
    </Modal>
  );
}
