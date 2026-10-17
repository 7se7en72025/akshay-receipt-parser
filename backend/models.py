import math
import re
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

Number = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]
NonNegative = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(default="", max_length=2000)
    hsn: str = Field(default="", max_length=32)
    quantity: NonNegative | None = None
    unit: str = Field(default="", max_length=32)
    unit_price: NonNegative | None = None
    discount_1: Number | None = None
    discount_2: Number | None = None
    taxable_amount: Number | None = None
    sgst_rate: NonNegative | None = None
    sgst_amount: Number | None = None
    cgst_rate: NonNegative | None = None
    cgst_amount: Number | None = None
    igst_rate: NonNegative | None = None
    igst_amount: Number | None = None
    cess_amount: Number | None = None
    source_page: int = Field(default=1, ge=1, le=25)
    secondary_amount: Number | None = None
    secondary_currency: str = Field(default="", pattern=r"^(?:[A-Z]{3})?$")

    @field_validator("*", mode="before")
    @classmethod
    def empty_numbers(cls, value, info):
        numeric = {
            "quantity",
            "unit_price",
            "discount_1",
            "discount_2",
            "taxable_amount",
            "sgst_rate",
            "sgst_amount",
            "cgst_rate",
            "cgst_amount",
            "igst_rate",
            "igst_amount",
            "cess_amount",
        }
        if info.field_name in numeric and value == "":
            return None
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Numbers must be finite.")
        return value


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_name: str = Field(default="", max_length=300)
    supplier_gstin: str = Field(default="", max_length=32)
    bill_number: str = Field(default="", max_length=150)
    bill_date: date | None = None
    purchase_number: str = Field(default="", max_length=150)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    other_tax_total: Number | None = None
    charges_total: Number | None = None
    discount_total: Number | None = None
    withholding_total: Number | None = None
    amounts_include_tax: bool = False
    secondary_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    secondary_subtotal: Number | None = None
    exchange_rate: Number | None = None
    taxable_total: Number | None = None
    sgst_total: Number | None = None
    cgst_total: Number | None = None
    igst_total: Number | None = None
    cess_total: Number | None = None
    round_off: Number | None = None
    grand_total: Number | None = None
    items: list[Item] = Field(default_factory=list, max_length=1500)
    notes: str = Field(default="", max_length=4000)

    @field_validator(
        "bill_date",
        "taxable_total",
        "sgst_total",
        "cgst_total",
        "igst_total",
        "cess_total",
        "round_off",
        "grand_total",
        "other_tax_total",
        "charges_total",
        "discount_total",
        "withholding_total",
        "secondary_subtotal",
        "exchange_rate",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value):
        return None if value == "" else value


class SaveRequest(BaseModel):
    invoice: Invoice
    version: int = Field(ge=1)


class ApproveRequest(SaveRequest):
    acknowledge_warnings: bool = False
    review_note: str = Field(default="", max_length=1000)


class ExportRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=200)
    template_id: str | None = None


class TemplateConfig(BaseModel):
    sheet_name: str
    header_row: int = Field(default=1, ge=1, le=200)
    start_row: int = Field(default=2, ge=2, le=100000)
    mapping: dict[str, int] = Field(default_factory=dict, max_length=60)


def number(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    text = re.sub(r"^(?:INR|USD|EUR|GBP|NAD|ZAR|ZMW|US\$|N\$|R|K|[$₹£€])\s*", "", text, flags=re.I)
    text = re.sub(r"\s*(?:INR|USD|EUR|GBP|NAD|ZAR|ZMW|[$₹£€%])$", "", text, flags=re.I)
    text = re.sub(r"\s+", "", text)
    if "," in text and "." in text:
        text = (
            text.replace(".", "").replace(",", ".")
            if text.rfind(",") > text.rfind(".")
            else text.replace(",", "")
        )
    elif "," in text:
        text = (
            text.replace(",", ".")
            if re.fullmatch(r"-?\d+,\d{1,2}", text)
            else text.replace(",", "")
        )
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    try:
        result = Decimal(text)
        return result if result.is_finite() else None
    except ArithmeticError:
        return None
