import unittest
from decimal import Decimal

from backend.extraction import header_fields, inline_quantity_items, table_items
from backend.layouts import borderless_tables, currency_value, generic_fields
from backend.models import number


class ImageLayoutTests(unittest.TestCase):
    def test_order_rows_copy_printed_quantities_and_amounts_without_inferred_rates(self):
        items = inline_quantity_items(
            "Order Summary\nCustomer  2.0 x Standard ticket  $60.00\nCustomer  1.0 �VIP pass  $75.00\nCustomer  3.0 xMerch package  $90.00",
            1,
        )
        self.assertEqual(
            [item.description for item in items], ["Standard ticket", "VIP pass", "Merch package"]
        )
        self.assertEqual([item.quantity for item in items], [Decimal(2), Decimal(1), Decimal(3)])
        self.assertEqual(
            [item.taxable_amount for item in items], [Decimal(60), Decimal(75), Decimal(90)]
        )
        self.assertTrue(all(item.unit_price is None for item in items))
        self.assertFalse(inline_quantity_items("Product dimensions\n2 x Wood panel  $60.00", 1))

    def test_one_bad_inline_amount_does_not_erase_the_quantity(self):
        items = inline_quantity_items(
            "Order Summary\nCustomer  2 x Ticket  $999999999999999999999999.00", 1
        )
        self.assertEqual(items[0].quantity, Decimal(2))
        self.assertIsNone(items[0].taxable_amount)

    def test_freelancer_hours_and_date_columns_map_without_date_in_description(self):
        words = self.words(
            [
                [
                    (10, 60, "Date"),
                    (100, 250, "Description of work"),
                    (300, 350, "Hours"),
                    (400, 450, "Rate"),
                    (500, 550, "Total"),
                ],
                [
                    (10, 60, "15/07/2023"),
                    (100, 250, "Writing service"),
                    (320, 350, "10.0"),
                    (400, 450, "C$50.00"),
                    (500, 550, "C$500.00"),
                ],
            ]
        )
        item = table_items(borderless_tables(words)[0], 1)[0]
        self.assertEqual(item.description, "Writing service")
        self.assertEqual(item.quantity, Decimal(10))
        self.assertEqual(item.unit_price, Decimal(50))
        self.assertEqual(item.taxable_amount, Decimal(500))

    def test_hours_unit_is_taken_from_the_printed_column_heading(self):
        item = table_items(
            [
                ["Description of work", "Hours", "Rate", "Total"],
                ["Writing", "5", "50.00", "250.00"],
            ],
            1,
        )[0]
        self.assertEqual(item.unit, "Hours")

    def test_aggregate_tax_does_not_duplicate_printed_gst_components(self):
        fields = generic_fields(
            "Example Supplier\nSubtotal 100.00\nCGST 9.00\nSGST 9.00\nTax 18.00\nTOTAL TAX 18.00\nTOTAL 118.00"
        )
        self.assertIsNone(fields.get("other_tax_total"))

    def test_separate_invoice_heading_does_not_capture_neighboring_supplier(self):
        source = "DATE\nPI 15/07/2023\nINVOICE NO.\nExample Seller  INV-2023-0098\nBILL TO\nCustomer\nSUBTOTAL  C$100.00\nTAX  C$5.00\nREMARKS/INSTRUCTIONS  TOTAL C$105.00\nMake checks payable to: Example Seller"
        fields = generic_fields(source)
        fields.update(header_fields(source))
        self.assertEqual(fields["supplier_name"], "Example Seller")
        self.assertEqual(fields["bill_number"], "INV-2023-0098")
        self.assertEqual(str(fields["bill_date"]), "2023-07-15")
        self.assertEqual(fields["other_tax_total"], Decimal(5))
        self.assertEqual(fields["grand_total"], Decimal(105))

    def test_currency_prefix_number_reading_does_not_convert_amounts(self):
        self.assertEqual(number("C$1,200.00"), Decimal(1200))
        self.assertEqual(number("A$25.50"), Decimal("25.50"))
        self.assertEqual(number("CAD 75.00"), Decimal(75))

    def test_bare_dollar_payable_does_not_override_currency_from_full_source(self):
        fields = generic_fields(
            "Example LLC\nMemphis, TN 38115\nSubtotal $100.00\nSales Tax $8.00\nTOTAL $108.00"
        )
        self.assertEqual(fields["currency"], "USD")
        self.assertIsNone(currency_value("TOTAL $108.00", default=None))

    def test_qty_slash_value_is_one_header_not_a_phantom_amount_column(self):
        words = self.words(
            [
                [
                    (10, 120, "Description"),
                    (230, 250, "Qty"),
                    (255, 260, "/"),
                    (265, 300, "Value"),
                    (350, 400, "Rate"),
                    (450, 500, "Amount"),
                ],
                [
                    (10, 180, "Printed freight"),
                    (285, 300, "1"),
                    (350, 400, "100.00"),
                    (450, 500, "100.00"),
                ],
            ]
        )
        table = borderless_tables(words)[0]
        self.assertEqual(table[0], ["description", "qty", "rate", "amount"])
        item = table_items(table, 1)[0]
        self.assertEqual(item.quantity, Decimal(1))
        self.assertEqual(item.taxable_amount, Decimal(100))

    def words(self, rows):
        result = []
        for row_index, row in enumerate(rows):
            for x, end, text in row:
                result.append({"x0": x, "x1": end, "top": row_index * 30, "text": text})
        return result

    def test_unit_price_and_value_are_separate_columns(self):
        words = self.words(
            [
                [
                    (10, 120, "Description"),
                    (250, 310, "Quantity"),
                    (350, 430, "Unit Price"),
                    (480, 530, "Value"),
                ],
                [
                    (10, 210, "Printed service"),
                    (285, 310, "3.00"),
                    (375, 430, "1500.00"),
                    (475, 530, "4500.00"),
                ],
            ]
        )
        item = table_items(borderless_tables(words)[0], 1)[0]
        self.assertEqual(item.quantity, Decimal(3))
        self.assertEqual(item.unit_price, Decimal(1500))
        self.assertEqual(item.taxable_amount, Decimal(4500))

    def test_thermal_rate_continuation_is_not_part_of_name(self):
        words = self.words(
            [
                [(10, 100, "Item"), (250, 300, "Qty"), (400, 480, "Amount")],
                [(10, 130, "Paper pack"), (260, 300, "10"), (430, 480, "37.50")],
                [(10, 150, "@ 3.75 each")],
                [(10, 150, "Single lamp"), (270, 300, "1"), (430, 480, "45.25")],
            ]
        )
        items = table_items(borderless_tables(words)[0], 1)
        self.assertEqual(items[0].description, "Paper pack")
        self.assertEqual(items[0].unit_price, Decimal("3.75"))
        self.assertEqual(items[1].description, "Single lamp")
        self.assertIsNone(items[1].unit_price)  # No printed rate; do not infer it.

    def test_wrapped_supplier_omits_neighboring_phone(self):
        fields = generic_fields(
            "Example Office Supplies  +353 1234567\nLtd\nInvoice Number: TEST-1"
        )
        self.assertEqual(fields["supplier_name"], "Example Office Supplies Ltd")

    def test_receipt_number_and_named_order_date(self):
        fields = generic_fields(
            "Order Summary\nOrder #INV-20230715-001 - 15 July 2023\n$722.25 paid by Card\nThis order is subject to Event Company Inc. Terms of Service"
        )
        self.assertEqual(fields["bill_number"], "INV-20230715-001")
        self.assertEqual(str(fields["bill_date"]), "2023-07-15")
        self.assertEqual(fields["grand_total"], Decimal("722.25"))
        self.assertEqual(fields["supplier_name"], "Event Company Inc.")

    def test_neighboring_footer_keeps_net_and_tax_amounts(self):
        fields = generic_fields(
            "Example Ltd\nEUR SALES INVOICE\nVAT % Net VAT NET TOTAL  6200.00\nAnalysis VAT TOTAL  1143.00\nEUR TOTAL  7343.00"
        )
        self.assertEqual(fields["taxable_total"], Decimal(6200))
        self.assertEqual(fields["other_tax_total"], Decimal(1143))
        self.assertEqual(fields["grand_total"], Decimal(7343))

    def test_ambiguous_dollars_never_default_to_rupees(self):
        self.assertEqual(currency_value("TOTAL $42.00"), "UNK")
        self.assertEqual(currency_value("TOTAL CAD 42.00"), "CAD")
        self.assertEqual(currency_value("TOTAL AUD 42.00"), "AUD")
        self.assertEqual(currency_value("TOTAL INR 42.00"), "INR")
