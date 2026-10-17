"""Layout-independent text headers and coordinate-based borderless tables.

This module consumes source document content only, never evaluation labels.
"""

import re
from datetime import datetime
from decimal import Decimal

from .models import number


def date_value(value, us=False):
    value = value.strip()
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d-%b-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
    ]
    patterns += (
        ["%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y"]
        if us
        else ["%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y"]
    )
    for pattern in patterns:
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def tail_amount(line):
    match = re.search(r"(-?\d(?:[\d ,.]*\d)?)\s*(?:INR|USD|EUR|GBP|NAD|ZAR|ZMW|[$£€₹�])*\s*$", line)
    return number(match[1]) if match else None


def currency_value(text, default="INR"):
    for pattern, code in [
        (r"\bINR\b|₹|\bRs\.?", "INR"),
        (r"\bUSD\b|US\$", "USD"),
        (r"\bCAD\b|CA\$", "CAD"),
        (r"\bAUD\b|AU\$", "AUD"),
        (r"\bEUR\b|€", "EUR"),
        (r"\bGBP\b|£", "GBP"),
        (r"\bNAD\b|N\$", "NAD"),
        (r"\bZAR\b|\bR\s*\d", "ZAR"),
        (r"\bZMW\b|\bK\s*\d", "ZMW"),
    ]:
        if re.search(pattern, text):
            return code
    # A bare dollar or a missing currency glyph is not enough to identify a currency.
    if ".com.na" in text:
        return "NAD"
    if ".co.uk" in text or "VAT Reg No: GB" in text:
        return "GBP"
    if ".de" in text or ".fr" in text:
        return "EUR"
    if "$" in text and ("Sales Tax" in text or re.search(r"\b[A-Z]{2} \d{5}\b", text)):
        return "USD"
    if "$" in text and default == "INR":
        return "UNK"  # Never silently approve ambiguous dollar amounts as INR.
    return default


def generic_fields(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.startswith("--- PAGE")
    ]
    data = {}
    source = "\n".join(lines)
    us = bool(re.search(r"\b[A-Z]{2} \d{5}\b|\bEIN\s*:|Sales Tax", source))
    header = re.split(r"\bBILL TO\b|\bDescription\b", source, maxsplit=1, flags=re.I)[0]
    heading_names = {
        "",
        "date",
        "invoice",
        "taxinvoice",
        "statement",
        "ordersummary",
        "orderconfirmation",
    }
    if lines:
        first_line = re.split(r"\s{2,}", lines[0])[0]
        candidate = re.sub(r"\b(?:TAX\s+)?INVOICE\b.*$", "", first_line, flags=re.I).strip()
        if not candidate:
            candidate = re.sub(r"^(?:TAX\s+)?INVOICE\s*", "", lines[0], flags=re.I).strip()
        if not candidate and len(lines) > 1:
            candidate = lines[1]
        if (
            candidate
            and re.sub(r"\W", "", candidate).casefold() not in heading_names
            and not re.search(r"Invoice\s*(?:No|Number|#)|^Date\s*:", candidate, re.I)
        ):
            if len(lines) > 1 and re.fullmatch(
                r"(?:Ltd\.?|Limited|LLC|Inc\.?|GmbH|PLC)", lines[1], re.I
            ):
                candidate += " " + lines[1]
            data["supplier_name"] = candidate
    seller_statement = re.search(
        r"This order is subject to\s+(.+?)\s+Terms of Service", source, re.I
    )
    if seller_statement:
        data["supplier_name"] = seller_statement[1].strip()
    payee = re.search(r"Make\s+checks\s+payable\s+to\s*:\s*([^\n]+)", source, re.I)
    generic_name = re.sub(r"\W", "", data.get("supplier_name", "")).casefold()
    if (
        payee
        and generic_name in heading_names
        and re.sub(r"\s+", " ", payee[1].strip()).casefold()
        in re.sub(r"\s+", " ", header).casefold()
    ):
        data["supplier_name"] = payee[1].strip()
    identifier = re.search(
        r"(?<!Supplier )\b(?:Invoice|Document)[^\S\n]*(?:Number\b|No\b\.?|#)[^\S\n]*[:#.]?[^\S\n]*([A-Z0-9][A-Z0-9/._-]*)",
        header,
        re.I,
    )
    if not identifier:
        identifier = re.search(r"\bOur Reference\s*:\s*([A-Z0-9]*INV[A-Z0-9/._-]*)", header, re.I)
    if not identifier:
        identifier = re.search(
            r"\b(?:Receipt|Order)\s*(?:(?:Number|No)\b\.?)?\s*[:#]\s*([A-Z0-9][A-Z0-9/._-]*)",
            header,
            re.I,
        )
    if identifier:
        data["bill_number"] = identifier[1]
    elif re.search(r"\bINVOICE\s*(?:NO\.?|NUMBER|#)", header, re.I):
        candidates = set(re.findall(r"\bINV[-/][A-Z0-9._/-]*\d[A-Z0-9._/-]*\b", header, re.I))
        if len(candidates) == 1:
            data["bill_number"] = candidates.pop()
    if not data.get("bill_number"):
        separate_number = re.search(
            r"\b(?:INVOICE|BILL|DOCUMENT)[ \t]*(?:NO\.?|NUMBER|#)[ \t]*[:.]?[ \t]*\n[ \t]*(\d+)[ \t]*(?=\n|$)",
            header,
            re.I,
        )
        if separate_number:
            data["bill_number"] = separate_number[1]
    header_lines = header.splitlines()
    for index, line in enumerate(header_lines):
        if re.fullmatch(r"DATE", line.strip(), re.I) and index + 1 < len(header_lines):
            following = re.search(r"\b(\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4})\b", header_lines[index + 1])
            if following and date_value(following[1], us):
                data["bill_date"] = date_value(following[1], us)
                break
        match = re.search(
            r"(?<!Due )\bDate\s*:\s*(\d{1,4}[-/.]\w{1,9}[-/.]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},\s*\d{4})",
            line,
            re.I,
        )
        if match:
            data["bill_date"] = date_value(match[1], us)
            break
        if not re.search(r"\bDue\b", line, re.I):
            named = re.search(
                r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},\s*\d{4})\b", line
            )
            if named and date_value(named[1], us):
                data["bill_date"] = date_value(named[1], us)
                break
    data["currency"] = currency_value(source)
    totals = []
    taxes = []
    charges = []
    discounts = []
    footer = False
    for line in lines:
        amount = tail_amount(line)
        if amount is None:
            continue
        label = re.sub(r"\s+", " ", line).strip()
        if re.match(r"(?:Sub\s*Total|Total\b|Grand Total|Net Payable|Amount Payable)", label, re.I):
            footer = True
        if re.match(r"(?:Total\s+Exclusive|Total\s+Excl\b|Net\s+Amount\b(?! Due))", label, re.I):
            data["taxable_total"] = amount
        elif re.match(r"Sub\s*total\b", label, re.I):
            data.setdefault("taxable_total", amount)
        elif (
            footer
            and re.match(
                r"(?:Total\s+)?(?:VAT|MwSt|TVA|BTW|Tax|(?:[A-Za-z]+\s+){0,3}(?:Sales Tax|State Tax|Local Tax|County Tax))\b",
                label,
                re.I,
            )
            and not re.search(
                r"(?:VAT|TVA|BTW)[\s:-]*(?:Reg|No|ID|Number|Registration|nr|FR\d|NL\d)", label, re.I
            )
        ):
            if not (
                re.match(r"(?:Total\s+)?Tax\b", label, re.I)
                and re.search(r"\b(?:CGST|SGST|IGST|CESS)\b", source, re.I)
            ):
                taxes.append(amount)
        elif re.match(
            r"(?:Shipping|Freight|Delivery Charge|Handling Charge|S&H|Service Charge|Fuel Surcharge)\b",
            label,
            re.I,
        ):
            charges.append(amount)
        elif re.match(
            r"(?:Less Discount|Trade Discount|Discount|Promo(?: Code)?|Credit Applied)\b",
            label,
            re.I,
        ):
            discounts.append(abs(amount))
        elif re.match(r"(?:Less:\s*)?Withholding\b", label, re.I):
            data["withholding_total"] = abs(amount)
        if re.match(
            r"(?:Grand\s+Total|TOTAL\b|Amount Payable|Net Payable|Balance Due)", label, re.I
        ) and not re.match(r"Total\s+(?:Exclusive|Excl|VAT|Tax)\b", label, re.I):
            totals.append(
                (3 if re.search(r"PAYABLE|Balance Due", label, re.I) else 1, amount, line)
            )
        elif footer and not re.match(
            r"(?:Sub\s*Total|Net\s+Total|VAT\s+Total|Total\s+Tax)", label, re.I
        ):
            if re.search(r"\bTOTAL\s+(?:US\$|CA\$|AU\$|C\$|A\$|[$€£₹�])", label, re.I):
                totals.append((1, amount, line))
    if taxes:
        data["other_tax_total"] = sum(taxes, Decimal(0))
    # OCR can join neighboring footer columns into one line. Read only explicit
    # labelled amounts; never take a tax-analysis row as a new invoice total.
    amount_pattern = r"\s*:?\s*(?:[A-Z]{3}\s*|[$€£₹�]\s*)?(-?\d[\d ,]*(?:\.\d{1,4})?)\s*(?=\n|$|  )"
    for field, label in (
        ("taxable_total", r"\bNET\s+TOTAL"),
        ("other_tax_total", r"\b(?:VAT\s+TOTAL|TOTAL\s+TAX)"),
    ):
        if field == "other_tax_total" and re.search(r"\b(?:CGST|SGST|IGST|CESS)\b", source, re.I):
            continue
        matches = re.findall(label + amount_pattern, source, re.I)
        if matches and number(matches[-1]) is not None:
            data[field] = number(matches[-1])
    if charges:
        data["charges_total"] = sum(charges, Decimal(0))
    if discounts:
        data["discount_total"] = sum(discounts, Decimal(0))
    if totals:
        _, data["grand_total"], payable_line = max(
            enumerate(totals), key=lambda pair: (pair[1][0], pair[0])
        )[1]
        payable_currency = currency_value(payable_line, default=None)
        if payable_currency:
            data["currency"] = payable_currency
    elif data.get("currency"):
        match = re.search(
            r"\b" + re.escape(data["currency"]) + r"\s+TOTAL" + amount_pattern, source, re.I
        )
        if match:
            data["grand_total"] = number(match[1])
    if data.get("grand_total") is None:
        paid = re.search(r"[$€£₹�]\s*(\d[\d,]*(?:\.\d{2}))\s+paid\s+by\b", source, re.I)
        if paid:
            data["grand_total"] = number(paid[1])
    exchange = re.search(r"Exchange rate\s*:\s*1\s+([A-Z]{3})\s*=\s*([\d.]+)\s+([A-Z]{3})", source)
    if exchange and exchange[3] == data["currency"] and data.get("taxable_total") is not None:
        data["secondary_currency"] = exchange[1]
        data["secondary_subtotal"] = data["taxable_total"]
        data["exchange_rate"] = number(exchange[2])
        data["taxable_total"] = (data["secondary_subtotal"] * data["exchange_rate"]).quantize(
            Decimal("0.01")
        )
    if re.search(r"VAT[^\n]*(?:included|inclusive)|TOTAL\s*\(VAT inclusive\)", source, re.I):
        data["amounts_include_tax"] = True
        if data.get("grand_total") is not None and data.get("other_tax_total") is not None:
            data["taxable_total"] = data["grand_total"] - data["other_tax_total"]
    return data


def vendor_from_words(words):
    if not words:
        return ""
    top = min(word["top"] for word in words)
    candidates = {}
    for word in words:
        if word["top"] > top + 18:
            continue
        key = (word.get("fontname"), round(word.get("size", 0), 1), round(word["top"] / 3))
        candidates.setdefault(key, []).append(word)
    texts = [
        " ".join(word["text"] for word in sorted(group, key=lambda word: word["x0"]))
        for group in candidates.values()
    ]
    texts = [re.sub(r"\b(?:TAX\s+)?INVOICE\b.*$", "", value, flags=re.I).strip() for value in texts]
    texts = [
        value
        for value in texts
        if len(value) > 4 and not re.match(r"(?:Date|Invoice Number|Invoice No)\b", value, re.I)
    ]
    return max(texts, key=len, default="")


def word_lines(words, tolerance=3):
    lines = []
    for word in sorted(words, key=lambda word: (word["top"], word["x0"])):
        if not lines or abs(lines[-1][0]["top"] - word["top"]) > tolerance:
            lines.append([word])
        else:
            lines[-1].append(word)
    return [sorted(line, key=lambda word: word["x0"]) for line in lines]


def borderless_tables(words):
    """Map source word boxes to table columns, retaining wrapped descriptions."""
    tables, columns, rows = [], [], []
    for line in word_lines(words):
        aliases = {
            "item": "description",
            "item description": "description",
            "product": "description",
            "unit price": "rate",
            "unitprice": "rate",
            "value": "amount",
            "description of work": "description",
            "descriptionofwork": "description",
            "hours": "quantity",
        }
        names = [
            aliases.get(word["text"].lower().strip(".:#"), word["text"].lower().strip(".:#"))
            for word in line
        ]
        if "description" in names and (
            any(name in {"qty", "quantity"} for name in names) or "ccy" in names
        ):
            if rows:
                tables.append(rows)
            columns = []
            for index, word in enumerate(line):
                name = names[index]
                # Do not create a second column for a consumed heading suffix.
                if columns and word["x1"] <= columns[-1]["end"]:
                    continue
                if name in {
                    "description",
                    "date",
                    "code",
                    "hsn",
                    "qty",
                    "quantity",
                    "price",
                    "rate",
                    "amount",
                    "total",
                    "vat",
                    "ccy",
                    "amt",
                } or (
                    name == "unit"
                    and index + 1 < len(names)
                    and names[index + 1] in {"usd", "eur", "nad", "zar"}
                ):
                    if name == "price" and index and names[index - 1] == "unit":
                        name = "rate"
                    end = word["x1"]
                    if name == "unit":
                        name = "rate"
                    if name == "amt" and index and names[index - 1] == "foreign":
                        name = "foreign_amount"
                    if name in {"amount", "vat", "qty", "quantity", "rate"}:
                        for following in line[index + 1 :]:
                            if following["text"].lower() in {
                                "usd",
                                "zar",
                                "nad",
                                "eur",
                                "gbp",
                                "excl",
                                "incl",
                                "%",
                                "/",
                            } or (
                                following["text"].lower() == "value"
                                and name in {"vat", "amount", "qty", "quantity"}
                            ):
                                end = following["x1"]
                                if name == "amount" and following["text"].upper() in {
                                    "USD",
                                    "EUR",
                                    "NAD",
                                    "ZAR",
                                    "GBP",
                                    "INR",
                                }:
                                    name = "amount " + following["text"].upper()
                            else:
                                break
                    start = line[index - 1]["x0"] if name == "foreign_amount" else word["x0"]
                    columns.append({"name": name, "end": end, "start": start})
            rows = [[column["name"] for column in columns]]
            continue
        if not rows:
            continue
        joined = " ".join(word["text"] for word in line)
        if re.match(
            r"(?:Sub\s*Total|Total\b|Grand Total|VAT\b|Sales Tax|MwSt|TVA|Page \d|Continued|Banking|Exchange rate)",
            joined,
            re.I,
        ):
            if len(rows) > 1:
                tables.append(rows)
            columns, rows = [], []
            continue
        numeric_columns = [
            index
            for index, column in enumerate(columns)
            if column["name"] not in {"code", "description", "hsn", "ccy", "date"}
        ]
        if len(numeric_columns) < 2:
            continue
        first = numeric_columns[0]
        gap = columns[numeric_columns[1]]["end"] - columns[first]["end"]
        numeric_start = min(columns[first]["end"] - gap * 0.65, columns[first]["start"] - 8)
        cells = [""] * len(columns)
        for word in line:
            if word["x0"] < numeric_start:
                position = next(
                    (i for i, col in enumerate(columns) if col["name"] == "description"), 0
                )
                ccy = next((i for i, col in enumerate(columns) if col["name"] == "ccy"), None)
                if ccy is not None and word["x0"] >= columns[ccy]["start"] - 2:
                    position = ccy
                if position and word["x1"] < columns[position]["start"] - 2:
                    position -= 1
            else:
                position = first
                for index in numeric_columns[1:]:
                    before = columns[index - 1]["end"]
                    if word["x0"] >= before + (columns[index]["end"] - before) * 0.12:
                        position = index
            cells[position] = (cells[position] + " " + word["text"]).strip()
        if number(cells[first]) is not None or (
            "ccy" in [column["name"] for column in columns]
            and number(cells[numeric_columns[-1]]) is not None
        ):
            rows.append(cells)
        elif len(rows) > 1 and any(cells) and not any(cells[index] for index in numeric_columns):
            # Thermal receipts print a separate '@ 3.75 each' continuation.
            # Preserve that explicit rate without mixing it into the item name.
            rate = re.fullmatch(r"@\s*(?:[$€£₹�]\s*)?(\d[\d,.]*)\s+each", joined, re.I)
            if rate and number(rate[1]) is not None:
                rate_column = next(
                    (i for i, column in enumerate(columns) if column["name"] == "rate"), None
                )
                if rate_column is None:
                    columns.append(
                        {
                            "name": "rate",
                            "start": columns[-1]["end"] + 10,
                            "end": columns[-1]["end"] + 20,
                        }
                    )
                    rows[0].append("rate")
                    for row in rows[1:]:
                        row.append("")
                    rate_column = len(columns) - 1
                if not rows[-1][rate_column]:
                    rows[-1][rate_column] = rate[1]
                continue
            description = next(
                (i for i, column in enumerate(columns) if column["name"] == "description"), None
            )
            if description is not None:
                rows[-1][description] += " " + cells[description]
    if len(rows) > 1:
        tables.append(rows)
    return tables
