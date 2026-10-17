import { AlertCircle, CheckCircle2, Copy, ArrowRight } from "lucide-react";
import { Modal } from "./components";
import type { UploadResult } from "./types";

export function UploadReport({
  result,
  onClose,
  onOpen,
}: {
  result: UploadResult;
  onClose: () => void;
  onOpen: (id: string) => void;
}) {
  return (
    <Modal title="Last upload results" onClose={onClose}>
      <div className="modal-body upload-results">
        <p className="muted">
          {result.created.length} queued · {result.duplicates.length} duplicates
          · {result.errors.length} issues
        </p>
        <p className="section-description">
          Results stay available from Last upload until you upload another batch
          or reload the page. Queued bills continue processing in the
          background.
        </p>
        {result.errors.map((item, index) => (
          <div className="upload-result failed" key={"error-" + index}>
            <AlertCircle size={18} />
            <div>
              <strong>{item.filename}</strong>
              <p>{item.message}</p>
            </div>
          </div>
        ))}
        {result.duplicates.map((item) => (
          <div className="upload-result" key={"duplicate-" + item.id}>
            <Copy size={18} />
            <div>
              <strong>{item.filename}</strong>
              <p>Already uploaded. The existing bill is preserved.</p>
            </div>
            <button className="text-button" onClick={() => onOpen(item.id)}>
              Open <ArrowRight size={14} />
            </button>
          </div>
        ))}
        {result.created.map((item) => (
          <div className="upload-result" key={item.id}>
            <CheckCircle2 size={18} />
            <div>
              <strong>{item.filename}</strong>
              <p>Original saved and queued for extraction.</p>
            </div>
            <button className="text-button" onClick={() => onOpen(item.id)}>
              Review <ArrowRight size={14} />
            </button>
          </div>
        ))}
        {!result.created.length &&
          !result.duplicates.length &&
          !result.errors.length && <p>No files were processed.</p>}
      </div>
      <footer className="modal-footer">
        <button className="button secondary" onClick={onClose}>
          Done
        </button>
      </footer>
    </Modal>
  );
}
