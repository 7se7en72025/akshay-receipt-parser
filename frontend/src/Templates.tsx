import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  LoaderCircle,
  Plus,
  Save,
  ShieldCheck,
} from "lucide-react";
import { api, message } from "./api";
import { Loading } from "./components";
import { useUnsavedChanges } from "./useUnsavedChanges";
import type {
  Notify,
  Template,
  TemplateConfig,
  TemplateInspection,
} from "./types";

export function Templates({
  templates,
  fields,
  notify,
  onRefresh,
  onDirty,
  defaultFormat,
}: {
  templates: Template[];
  fields: Record<string, string>;
  notify: Notify;
  onRefresh: () => Promise<void>;
  onDirty: (dirty: boolean) => void;
  defaultFormat?: { sheets: Record<string, string[]> };
}) {
  const [selected, setSelected] = useState("");
  const [inspection, setInspection] = useState<TemplateInspection | null>(null);
  const [config, setConfig] = useState<TemplateConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [saved, setSaved] = useState(false);
  const [baseline, setBaseline] = useState("");
  const dirty = !!config && JSON.stringify(config) !== baseline;
  useUnsavedChanges(dirty, onDirty);
  const stale =
    !!config &&
    !!inspection &&
    (config.sheet_name !== inspection.sheet_name ||
      config.header_row !== inspection.header_row);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!selected && templates.length) setSelected(templates[0].id);
  }, [selected, templates]);
  useEffect(() => {
    if (!selected) return;
    let canceled = false;
    setLoading(true);
    setInspection(null);
    setConfig(null);
    const existing = templates.find(
      (template) => template.id === selected,
    )?.config;
    const query = existing?.sheet_name
      ? "?sheet_name=" +
        encodeURIComponent(existing.sheet_name) +
        "&header_row=" +
        existing.header_row
      : "";
    void api<TemplateInspection>("/templates/" + selected + "/inspect" + query)
      .then((result) => {
        if (canceled) return;
        setInspection(result);
        const next = {
          sheet_name: result.sheet_name,
          header_row: result.header_row,
          start_row: existing?.start_row || result.suggested_start_row,
          mapping: existing?.mapping || result.suggested_mapping,
        };
        setConfig(next);
        setBaseline(JSON.stringify(next));
        setSaved(
          !!existing?.mapping && Object.keys(existing.mapping).length > 0,
        );
      })
      .catch((error) => {
        if (!canceled) notify(message(error), true);
      })
      .finally(() => {
        if (!canceled) setLoading(false);
      });
    return () => {
      canceled = true;
    };
    // Selecting a template intentionally loads its saved configuration once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);
  async function upload(file: File) {
    if (
      dirty &&
      !window.confirm(
        "Discard the unsaved mapping and attach another template?",
      )
    )
      return;
    if (
      !file.size ||
      file.size > 15 * 1024 * 1024 ||
      !file.name.toLowerCase().endsWith(".xlsx")
    ) {
      notify("Choose a non-empty .xlsx workbook up to 15 MB.", true);
      if (input.current) input.current.value = "";
      return;
    }
    setBusy("upload");
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api<{ id: string }>("/templates", {
        method: "POST",
        body: form,
      });
      await onRefresh();
      setSelected(result.id);
      notify(
        "Template attached. Confirm its sheet, insertion row and column mapping.",
      );
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy("");
      if (input.current) input.current.value = "";
    }
  }
  async function readHeaders() {
    if (!config) return;
    setLoading(true);
    try {
      const result = await api<TemplateInspection>(
        "/templates/" +
          selected +
          "/inspect?sheet_name=" +
          encodeURIComponent(config.sheet_name) +
          "&header_row=" +
          config.header_row,
      );
      setInspection(result);
      setConfig({
        ...config,
        mapping: result.suggested_mapping,
        start_row:
          config.sheet_name !== inspection?.sheet_name
            ? result.suggested_start_row
            : Math.max(config.start_row, config.header_row + 1),
      });
      setSaved(false);
    } catch (error) {
      notify(message(error), true);
    } finally {
      setLoading(false);
    }
  }
  async function save() {
    if (!config || stale) {
      notify(
        "Read headings for the selected worksheet and header row first.",
        true,
      );
      return;
    }
    setBusy("save");
    try {
      await api("/templates/" + selected, {
        method: "PUT",
        body: JSON.stringify(config),
      });
      await onRefresh();
      setSaved(true);
      setBaseline(JSON.stringify(config));
      notify("Column mapping saved. This template is available during export.");
    } catch (error) {
      notify(message(error), true);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR EXCEL FORMAT</span>
          <h1>Excel templates</h1>
          <p>Keep the format your team already uses.</p>
        </div>
        <button
          className="button primary"
          disabled={!!busy}
          onClick={() => input.current?.click()}
        >
          {busy === "upload" ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Plus size={16} />
          )}
          Attach .xlsx template
        </button>
      </div>
      <input
        hidden
        type="file"
        accept=".xlsx"
        ref={input}
        onChange={(event) =>
          event.target.files?.[0] && void upload(event.target.files[0])
        }
      />
      <div className="panel default-format-card">
        <div className="default-format-heading">
          <span className="file-icon excel">
            <FileSpreadsheet size={25} />
          </span>
          <div>
            <h3>Default Excel format</h3>
            <p>Built in · Fixed columns · No setup needed</p>
          </div>
          <span className="status approved">
            <ShieldCheck size={13} />
            Always available
          </span>
        </div>
        <p>
          Export approved bills into Line Items and Bill Summary. This built-in
          format cannot be remapped or edited in the app. Custom workbooks are a
          separate option below.
        </p>
        <a className="button secondary" href="/api/templates/default/download">
          Download blank format
        </a>
        <details className="default-format-columns">
          <summary>View fixed columns</summary>
          {Object.entries(defaultFormat?.sheets || {}).map(
            ([name, columns]) => (
              <section key={name}>
                <h4>{name}</h4>
                <div>
                  {columns.map((column) => (
                    <span key={column}>{column}</span>
                  ))}
                </div>
              </section>
            ),
          )}
          {!defaultFormat && (
            <p>Column preview will load when the local backend connects.</p>
          )}
        </details>
      </div>
      <div className="notice info-note">
        <ShieldCheck size={22} />
        <div>
          <strong>Your original workbook stays unchanged</strong>
          <p>
            Choose where approved rows should go. Occupied cells and formula
            cells are never overwritten.
          </p>
        </div>
      </div>
      {!templates.length ? (
        <div className="panel empty">
          <FileSpreadsheet size={38} />
          <h3>Bring your own Excel sheet</h3>
          <p>
            Attach a workbook, select its headings, and map the invoice fields.
          </p>
          <button
            className="button secondary"
            onClick={() => input.current?.click()}
          >
            <Plus size={16} />
            Attach template
          </button>
          <small>
            You can also export using the standard workbook without a template.
          </small>
        </div>
      ) : (
        <div className="template-layout">
          <div className="template-list">
            {templates.map((template) => (
              <button
                key={template.id}
                className={
                  "panel template-card " +
                  (selected === template.id ? "selected" : "")
                }
                disabled={!!busy || loading}
                onClick={() => {
                  if (template.id === selected) return;
                  if (
                    !dirty ||
                    window.confirm("Discard the unsaved column mapping?")
                  )
                    setSelected(template.id);
                }}
              >
                <span className="file-icon excel">
                  <FileSpreadsheet size={23} />
                </span>
                <strong>{template.filename}</strong>
                <span
                  className={
                    template.config.mapping &&
                    Object.keys(template.config.mapping).length
                      ? "mapped"
                      : "muted"
                  }
                >
                  {template.config.mapping &&
                  Object.keys(template.config.mapping).length ? (
                    <>
                      <CheckCircle2 size={13} />
                      Mapping saved
                    </>
                  ) : (
                    "Mapping needed"
                  )}
                </span>
              </button>
            ))}
          </div>
          <div className="panel template-editor">
            {loading ? (
              <Loading label="Reading workbook headings…" />
            ) : config && inspection ? (
              <fieldset className="template-controls" disabled={!!busy}>
                <div className="panel-heading">
                  <div>
                    <FileSpreadsheet size={17} />
                    <strong>Worksheet & column mapping</strong>
                  </div>
                  {saved && (
                    <span className="status approved">
                      <CheckCircle2 size={12} />
                      Saved
                    </span>
                  )}
                </div>
                <div className="template-settings">
                  <label className="field">
                    <span>Worksheet</span>
                    <select
                      value={config.sheet_name}
                      onChange={(event) => {
                        setConfig({
                          ...config,
                          sheet_name: event.target.value,
                        });
                        setSaved(false);
                      }}
                    >
                      {inspection.sheet_names.map((name) => (
                        <option key={name}>{name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>Header row</span>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={config.header_row}
                      onChange={(event) => {
                        setConfig({
                          ...config,
                          header_row: Number(event.target.value),
                        });
                        setSaved(false);
                      }}
                    />
                  </label>
                  <label className="field">
                    <span>First empty insertion row</span>
                    <input
                      type="number"
                      min={config.header_row + 1}
                      max={100000}
                      value={config.start_row}
                      onChange={(event) => {
                        setConfig({
                          ...config,
                          start_row: Number(event.target.value),
                        });
                        setSaved(false);
                      }}
                    />
                  </label>
                  <button
                    className="button secondary small"
                    onClick={() => void readHeaders()}
                  >
                    Read headings
                  </button>
                </div>
                <p className="template-instructions">
                  Map each Excel column to an invoice field. Leave unused
                  columns unmapped. Confirm the insertion row is empty.
                </p>
                {stale && (
                  <p className="info-note">
                    Worksheet or header row changed. Select Read headings before
                    mapping or saving.
                  </p>
                )}
                <div className="table-wrap">
                  <table className="mapping-table">
                    <thead>
                      <tr>
                        <th>Excel column</th>
                        <th />
                        <th>Invoice field</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inspection.columns.map((column) => {
                        const current =
                          Object.keys(config.mapping).find(
                            (key) => config.mapping[key] === column.index,
                          ) || "";
                        return (
                          <tr key={column.index}>
                            <td>
                              <span className="column-letter">
                                {column.letter}
                              </span>
                              <strong>{column.label}</strong>
                            </td>
                            <td>
                              <ArrowRight size={15} />
                            </td>
                            <td>
                              <select
                                aria-label={"Map column " + column.letter}
                                value={current}
                                disabled={stale}
                                onChange={(event) => {
                                  const mapping = { ...config.mapping };
                                  Object.keys(mapping).forEach((key) => {
                                    if (mapping[key] === column.index)
                                      delete mapping[key];
                                  });
                                  if (event.target.value)
                                    mapping[event.target.value] = column.index;
                                  setConfig({ ...config, mapping });
                                  setSaved(false);
                                }}
                              >
                                <option value="">Leave unmapped</option>
                                {Object.entries(fields).map(([key, label]) => (
                                  <option
                                    key={key}
                                    value={key}
                                    disabled={
                                      key in config.mapping &&
                                      config.mapping[key] !== column.index
                                    }
                                  >
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="template-save">
                  <span>
                    {Object.keys(config.mapping).length} field(s) mapped
                    {dirty ? " · Unsaved changes" : ""}
                  </span>
                  <button
                    className="button primary"
                    disabled={
                      !!busy || stale || !Object.keys(config.mapping).length
                    }
                    onClick={() => void save()}
                  >
                    {busy === "save" ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <Save size={16} />
                    )}
                    Save mapping
                  </button>
                </div>
              </fieldset>
            ) : (
              <div className="empty">
                <h3>Select a template</h3>
                <p>Choose a workbook to configure its columns.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
