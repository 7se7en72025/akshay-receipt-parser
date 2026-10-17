import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageOps

from .config import MAX_IMAGE_PIXELS, MAX_PAGES
from .models import Invoice, Item, number

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def clean(value):
    return re.sub(r"[^a-z0-9%]", "", str(value or "").lower())


def parse_date(value):
    for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    return None


def header_fields(text):
    data = {}
    match = re.search(
        r"(?:bill|invoice)\s*(?:no\.?|number|#)\s*:?\s*([A-Z0-9][A-Z0-9./_-]+)",
        text,
        re.I,
    )
    if match:
        data["bill_number"] = match[1].strip()
    match = re.search(
        r"(?:bill|invoice)\s*date\s*:?\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4})",
        text,
        re.I,
    )
    if match:
        data["bill_date"] = parse_date(match[1])
    match = re.search(r"purchase\s*no\.?\s*:?\s*([A-Z0-9][A-Z0-9./_-]+)", text, re.I)
    if match:
        data["purchase_number"] = match[1]
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if re.search(r"purchased\s*from|supplier(?:\s*name)?\s*:", line, re.I):
            inline = re.split(r"supplier(?:\s*name)?\s*:", line, flags=re.I)
            candidate = inline[-1].strip() if len(inline) > 1 else ""
            if not candidate and index + 1 < len(lines):
                candidate = lines[index + 1]
            # Keep the supplier area, excluding a neighboring bill-number column.
            data["supplier_name"] = re.split(
                r"\s*(?:bill|invoice)\s*(?:no|date)", candidate, flags=re.I
            )[0].strip()
            block = "\n".join(lines[index : index + 7])
            gst = re.search(r"\b\d{2}[A-Z0-9]{13}\b", block)
            if gst:
                data["supplier_gstin"] = gst[0]
            break
    compact = re.sub(r"\s+", "", text)
    labels = {
        "taxable_total": r"TotalTaxableValue",
        "sgst_total": r"(?:SGST/UGST|SGSTTotal|TotalSGST)",
        "cgst_total": r"(?:CGSTTotal|TotalCGST|CGST)",
        "igst_total": r"(?:IGSTTotal|TotalIGST|IGST)",
        "cess_total": r"(?:TotalCess|CessTotal|CESS)",
        "round_off": r"Round(?:Off|ing)",
        "grand_total": r"(?:GrandTotal(?:\(INR\))?|AmountPayable|NetPayable)",
    }
    for field, label in labels.items():
        found = re.findall(label + r"[:₹]*(-?[\d,]+(?:\.\d+)?)", compact, re.I)
        if found:
            data[field] = number(found[-1])
    return data


def column_field(parent, child, discount_index):
    name = clean(parent)
    child_name = clean(child)
    if name in {"srno", "sno", "serialno", "no", "itemno"}:
        return None
    if name in {
        "description",
        "descriptionofgoods",
        "itemdescription",
        "particulars",
        "product",
        "productname",
        "itemname",
        "goodsdescription",
        "descriptionofitems",
    }:
        return "description"
    if name.startswith("hsn"):
        return "hsn"
    if name in {"qty", "quantity", "nos", "qnty", "qtyunit"}:
        return "quantity"
    if name in {"unit", "uom", "units"}:
        return "unit"
    if name in {"rate", "unitrate", "unitprice", "price"}:
        return "unit_price"
    if name.startswith(("disc", "discount")):
        return "discount_1" if discount_index <= 1 else "discount_2"
    if name.startswith("taxable") or name in {"amount", "amt", "value", "netamount"}:
        return "taxable_amount"
    for aliases, tax in [
        (("sugst", "sgst", "sgstugst", "utgst"), "sgst"),
        (("cgst",), "cgst"),
        (("igst",), "igst"),
        (("cess",), "cess"),
    ]:
        if any(name.startswith(alias) for alias in aliases):
            is_rate = "%" in name or "%" in child_name or child_name == "rate"
            return f"{tax}_rate" if is_rate and tax != "cess" else f"{tax}_amount"
    return None


def table_items(rows, page_number):
    result = []
    header_index = None
    for index, row in enumerate(rows):
        labels = [clean(cell) for cell in row]
        has_description = any(column_field(label, "", 0) == "description" for label in labels)
        has_quantity = any(column_field(label, "", 0) == "quantity" for label in labels)
        if has_description and has_quantity:
            header_index = index
            break
    if header_index is None:
        return []
    parents = rows[header_index]
    child = [""] * len(parents)
    data_start = header_index + 1
    if data_start < len(rows):
        possible_child = rows[data_start]
        tokens = [clean(cell) for cell in possible_child if cell]
        if tokens and all(
            token in {"%", "amt", "amount", "rate", "code", "no"} for token in tokens
        ):
            child = possible_child
            data_start += 1
    mapping = {}
    current = ""
    discount_index = 0
    for index, label in enumerate(parents):
        if label:
            current = label
            if clean(label).startswith(("disc", "discount")):
                discount_index += 1
        mapping[index] = column_field(
            current, child[index] if index < len(child) else "", discount_index
        )
    for row in rows[data_start:]:
        values = {"source_page": page_number}
        for index, cell in enumerate(row):
            field = mapping.get(index)
            if not field or not cell or field in values:
                continue
            value = re.sub(r"\s+", " ", str(cell)).strip()
            if field == "quantity":
                qty = re.match(r"^\s*([\d,.]+)\s*(.*?)\s*$", value)
                if qty:
                    values["quantity"] = number(qty[1])
                    if qty[2]:
                        values["unit"] = qty[2]
            elif field in {"description", "hsn", "unit"}:
                values[field] = value
            else:
                values[field] = number(value)
        description = values.get("description", "")
        has_serial = any(
            clean(parents[index]) in {"srno", "sno", "serialno", "no", "itemno"}
            and re.fullmatch(r"\d+", str(row[index] or "").strip())
            for index in range(min(len(parents), len(row)))
        )
        if (
            description
            and clean(description) not in {"total", "subtotal", "grandtotal"}
            and (
                values.get("quantity") is not None
                or has_serial
                or values.get("unit_price") is not None
                or values.get("taxable_amount") is not None
            )
        ):
            try:
                result.append(Item.model_validate(values))
            except ValueError:
                # Retain the row as a draft instead of silently losing the product.
                text_values = {
                    key: value
                    for key, value in values.items()
                    if key in {"description", "hsn", "unit", "source_page"}
                }
                result.append(Item.model_validate(text_values))
    return result


@lru_cache(maxsize=1)
def ocr_engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def ocr_page(image):
    import numpy as np

    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("Image exceeds the 25 megapixel processing limit.")
    # Limit long edges to keep OCR memory bounded in a local workspace.
    image.thumbnail((2400, 3200))
    output = ocr_engine()(np.asarray(image))
    if output.txts is None or output.boxes is None or output.scores is None:
        return "", [], []
    records = []
    for box, text, score in zip(output.boxes, output.txts, output.scores, strict=True):
        records.append(
            {
                "x": float(min(point[0] for point in box)),
                "y": float(sum(point[1] for point in box) / 4),
                "height": float(max(point[1] for point in box) - min(point[1] for point in box)),
                "text": text,
                "score": float(score),
            }
        )
    records.sort(key=lambda token: token["y"])
    lines = []
    for record in records:
        tolerance = max(6, record["height"] * 0.65)
        if not lines or abs(lines[-1]["y"] - record["y"]) > tolerance:
            lines.append({"y": record["y"], "tokens": [record]})
        else:
            lines[-1]["tokens"].append(record)
    for line in lines:
        line["tokens"].sort(key=lambda token: token["x"])
    text = "\n".join("  ".join(token["text"] for token in line["tokens"]) for line in lines)
    # Approximate columns from known headings. Unrecognised layouts remain review drafts.
    table = []
    for index, line in enumerate(lines):
        labels = [token["text"] for token in line["tokens"]]
        if any(column_field(label, "", 0) == "description" for label in labels) and any(
            column_field(label, "", 0) == "quantity" for label in labels
        ):
            header_tokens = line["tokens"]
            table.append(labels)
            for data_line in lines[index + 1 :]:
                cells = [""] * len(labels)
                for token in data_line["tokens"]:
                    position = min(
                        range(len(header_tokens)),
                        key=lambda i: abs(header_tokens[i]["x"] - token["x"]),
                    )
                    cells[position] = (cells[position] + " " + token["text"]).strip()
                table.append(cells)
            break
    return text, [table] if table else [], records


def extract_document(path: Path, mime: str):
    texts, tables, items, methods, notes = [], [], [], set(), []
    page_count = 1
    if mime == "application/pdf":
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            if not 1 <= page_count <= MAX_PAGES:
                raise ValueError(f"PDF must contain 1 to {MAX_PAGES} pages.")
            for page_index, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=1) or ""
                page_tables = page.extract_tables(table_settings={"text_x_tolerance": 1})
                large_image = any(
                    (image["x1"] - image["x0"]) * (image["bottom"] - image["top"])
                    > page.width * page.height * 0.4
                    for image in page.images
                )
                mapped_items = any(table_items(table, page_index + 1) for table in page_tables)
                if len(page_text.strip()) < 40 or (large_image and not mapped_items):
                    document = pdfium.PdfDocument(path)
                    try:
                        rendered_page = document[page_index]
                        try:
                            bitmap = rendered_page.render(scale=2)
                            try:
                                page_text, page_tables, _ = ocr_page(bitmap.to_pil())
                            finally:
                                bitmap.close()
                        finally:
                            rendered_page.close()
                    finally:
                        document.close()
                    methods.add("ocr")
                else:
                    methods.add("pdf")
                texts.append(f"--- PAGE {page_index + 1} ---\n{page_text}")
                for raw_table in page_tables:
                    tables.append({"page": page_index + 1, "rows": raw_table})
                    items.extend(table_items(raw_table, page_index + 1))
    else:
        with Image.open(path) as image:
            page_text, page_tables, _ = ocr_page(image)
        texts.append("--- PAGE 1 ---\n" + page_text)
        methods.add("ocr")
        for raw_table in page_tables:
            tables.append({"page": 1, "rows": raw_table})
            items.extend(table_items(raw_table, 1))
    raw_text = "\n\n".join(texts)
    invoice = Invoice(**header_fields(raw_text), items=items)
    # Missing printed zero-tax totals can be established from explicit per-row zeros.
    for prefix in ("sgst", "cgst", "igst", "cess"):
        total_field = prefix + "_total"
        values = [getattr(item, prefix + "_amount") for item in items]
        if getattr(invoice, total_field) is None and values and all(v is not None for v in values):
            setattr(invoice, total_field, sum(values))
            notes.append(f"{prefix.upper()} total was summed from the extracted item amounts.")
    if not items:
        notes.append(
            "No reliable item table was mapped. Add rows manually or use a configured local AI model."
        )
    if "ocr" in methods:
        notes.append("OCR was used. Check descriptions, decimal points and reconstructed columns.")
    if any(item.discount_1 is not None or item.discount_2 is not None for item in items):
        notes.append(
            "Discount columns are retained as printed; their conventions need staff confirmation."
        )
    return {
        "invoice": invoice,
        "raw_text": raw_text,
        "raw_tables": tables,
        "page_count": page_count,
        "method": "+".join(sorted(methods)),
        "notes": notes,
    }
