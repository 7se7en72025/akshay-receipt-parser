export type Amount = string | null;
export interface Item {
  secondary_amount: Amount;
  secondary_currency: string;
  description: string;
  hsn: string;
  quantity: Amount;
  unit: string;
  unit_price: Amount;
  discount_1: Amount;
  discount_2: Amount;
  taxable_amount: Amount;
  sgst_rate: Amount;
  sgst_amount: Amount;
  cgst_rate: Amount;
  cgst_amount: Amount;
  igst_rate: Amount;
  igst_amount: Amount;
  cess_amount: Amount;
  source_page: number;
}
export interface Invoice {
  currency: string;
  other_tax_total: Amount;
  charges_total: Amount;
  discount_total: Amount;
  withholding_total: Amount;
  amounts_include_tax: boolean;
  secondary_currency: string | null;
  secondary_subtotal: Amount;
  exchange_rate: Amount;
  supplier_name: string;
  supplier_gstin: string;
  bill_number: string;
  bill_date: string | null;
  purchase_number: string;
  taxable_total: Amount;
  sgst_total: Amount;
  cgst_total: Amount;
  igst_total: Amount;
  cess_total: Amount;
  round_off: Amount;
  grand_total: Amount;
  items: Item[];
  notes: string;
}
export interface Issue {
  level: "error" | "warning";
  field: string;
  message: string;
  row: number | null;
}
export interface Validation {
  issues: Issue[];
  errors: number;
  warnings: number;
  can_approve: boolean;
}
export interface Document {
  id: string;
  filename: string;
  status: "queued" | "processing" | "needs_review" | "approved" | "failed";
  invoice: Invoice;
  version: number;
  method: string;
  page_count: number;
  validation: Validation;
  extraction_notes: string[];
  created_at: string;
  updated_at: string;
  error: string | null;
  raw_text?: string;
  raw_tables?: unknown[];
  history?: { id: string; action: string; created_at: string }[];
}
export interface Health {
  default_format: {
    name: string;
    version: number;
    sheets: Record<string, string[]>;
  };
  status: string;
  workspace: string;
  ocr_installed: boolean;
  ai: { configured: boolean; available: boolean; model: string };
  vision: {
    configured: boolean;
    available: boolean;
    model: string;
    models: string[];
  };
  limits: { file_mb: number; batch_files: number; pages: number };
  export_fields: Record<string, string>;
}
export type DocumentSummary = Pick<
  Document,
  | "id"
  | "filename"
  | "status"
  | "method"
  | "page_count"
  | "version"
  | "error"
  | "created_at"
  | "updated_at"
> & {
  invoice: Pick<
    Invoice,
    "supplier_name" | "bill_number" | "bill_date" | "grand_total" | "currency"
  >;
};
export interface InboxPage {
  items: DocumentSummary[];
  total: number;
  matched: number;
  page: number;
  page_size: number;
  counts: { all: number; review: number; approved: number; processing: number };
  approved_value: string;
}
export interface UploadResult {
  created: { id: string; filename: string }[];
  duplicates: { id: string; filename: string }[];
  errors: { filename: string; message: string }[];
}
export interface HistoryRecord {
  id: string;
  action: string;
  created_at: string;
  invoice: Invoice | null;
  detail: { review_note?: string; method?: string; restored_from?: string };
}
export interface TemplateConfig {
  sheet_name: string;
  header_row: number;
  start_row: number;
  mapping: Record<string, number>;
}
export interface Template {
  id: string;
  filename: string;
  config: Partial<TemplateConfig>;
  created_at: string;
}
export interface TemplateInspection {
  sheet_names: string[];
  sheet_name: string;
  header_row: number;
  suggested_start_row: number;
  columns: {
    index: number;
    letter: string;
    label: string;
    suggested_field: string;
  }[];
  suggested_mapping: Record<string, number>;
}
export interface ExportRecord {
  id: string;
  created_at: string;
  documents: { id: string; version: number }[];
  rows: number;
  template_id: string | null;
}
export type Notify = (message: string, error?: boolean) => void;
export const emptyItem = (): Item => ({
  secondary_amount: null,
  secondary_currency: "",
  description: "",
  hsn: "",
  quantity: null,
  unit: "",
  unit_price: null,
  discount_1: null,
  discount_2: null,
  taxable_amount: null,
  sgst_rate: null,
  sgst_amount: null,
  cgst_rate: null,
  cgst_amount: null,
  igst_rate: null,
  igst_amount: null,
  cess_amount: null,
  source_page: 1,
});
