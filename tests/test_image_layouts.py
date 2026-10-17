import unittest
from decimal import Decimal

from backend.extraction import table_items
from backend.layouts import borderless_tables, currency_value, generic_fields


class ImageLayoutTests(unittest.TestCase):
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
