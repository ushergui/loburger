from decimal import Decimal

from django.test import SimpleTestCase

from core.utils import parse_numero_ptbr


class ParseNumeroPtBrTests(SimpleTestCase):
    def test_formato_brasileiro(self):
        self.assertEqual(parse_numero_ptbr('1.234,56'), Decimal('1234.56'))
        self.assertEqual(parse_numero_ptbr('2.500,00'), Decimal('2500.00'))
        self.assertEqual(parse_numero_ptbr('425,00'), Decimal('425.00'))
        self.assertEqual(parse_numero_ptbr('8,5'), Decimal('8.5'))
        self.assertEqual(parse_numero_ptbr('R$ 1.999,90'), Decimal('1999.90'))
        self.assertEqual(parse_numero_ptbr('5,450'), Decimal('5.450'))

    def test_aceita_ponto_decimal_tambem(self):
        self.assertEqual(parse_numero_ptbr('44.00'), Decimal('44.00'))
        self.assertEqual(parse_numero_ptbr('0.035'), Decimal('0.035'))
        self.assertEqual(parse_numero_ptbr('12'), Decimal('12'))

    def test_vazio_e_invalido(self):
        self.assertIsNone(parse_numero_ptbr(''))
        self.assertIsNone(parse_numero_ptbr(None))
        self.assertEqual(parse_numero_ptbr('abc', Decimal('0')), Decimal('0'))
        self.assertEqual(parse_numero_ptbr('', Decimal('0.00')), Decimal('0.00'))
