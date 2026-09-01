from decimal import Decimal
from django import forms
from .models import MovimentacaoEstoque
from produtos.forms import ThemeFormMixin


class CommaDecimalField(forms.DecimalField):
    def to_python(self, value):
        if value in (None, '', 'None'):
            return None
        if isinstance(value, Decimal):
            return value
        clean = str(value).replace('R$', '').replace(' ', '').replace(',', '.').strip()
        return super().to_python(clean)

TIPOS_MANUAIS = (
    ('ENTRADA', 'Entrada (Compra / Reposição) — gera despesa paga'),
    ('ABERTURA', 'Carga Inicial / Abertura — NÃO gera despesa'),
    ('SAIDA_PERDA', 'Saída por Perda / Descarte'),
    ('SAIDA_AUTOCONSUMO', 'Saída por Autoconsumo'),
    ('AJUSTE', 'Ajuste Geral de Inventário'),
)


class MovimentacaoEstoqueForm(ThemeFormMixin, forms.ModelForm):
    quantidade = CommaDecimalField(max_digits=10, decimal_places=2, label="Quantidade movimentada")
    valor_unitario = CommaDecimalField(
        max_digits=10, decimal_places=4, required=False,
        label="Custo unitário da compra (R$) — só para Entrada / Abertura",
    )

    class Meta:
        model = MovimentacaoEstoque
        fields = ['ingrediente', 'quantidade', 'tipo', 'valor_unitario', 'observacao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].choices = TIPOS_MANUAIS

    def clean(self):
        cleaned = super().clean()
        tipo = cleaned.get('tipo')
        if tipo in ('ENTRADA', 'ABERTURA') and not cleaned.get('valor_unitario'):
            self.add_error('valor_unitario', "Informe o custo unitário da compra para Entrada/Abertura.")
        return cleaned
