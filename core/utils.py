"""Utilitários de formatação e parsing em português do Brasil."""
from decimal import Decimal, InvalidOperation


def parse_numero_ptbr(valor, padrao=None):
    """Converte um texto em Decimal aceitando o formato brasileiro.

    Aceita: "1.234,56", "1234,56", "1234.56", "R$ 1.234,56", "8,5", "8", "".
    Regra: se tiver vírgula, ela é o separador decimal e o ponto é milhar;
    se não tiver vírgula, um único ponto é tratado como decimal.
    """
    if valor is None:
        return padrao
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    s = str(valor).replace('R$', '').replace('%', '').replace(' ', '').replace('\xa0', '').strip()
    if s in ('', 'None'):
        return padrao
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return padrao
