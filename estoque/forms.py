from decimal import Decimal
from django import forms
from core.utils import parse_numero_ptbr
from .models import MovimentacaoEstoque
from produtos.forms import ThemeFormMixin


class CommaDecimalField(forms.DecimalField):
    def to_python(self, value):
        if value in (None, '', 'None'):
            return None
        if isinstance(value, Decimal):
            return value
        return super().to_python(parse_numero_ptbr(value))

TIPOS_MANUAIS = (
    ('ENTRADA', 'Entrada (Compra / Reposição) — gera despesa paga'),
    ('ABERTURA', 'Carga Inicial / Abertura — NÃO gera despesa'),
    ('SAIDA_PERDA', 'Saída por Perda / Descarte'),
    ('SAIDA_AUTOCONSUMO', 'Saída por Autoconsumo'),
    ('AJUSTE', 'Ajuste Geral de Inventário'),
)


class MovimentacaoEstoqueForm(ThemeFormMixin, forms.ModelForm):
    quantidade = CommaDecimalField(
        max_digits=10, decimal_places=3, label="Quantidade movimentada",
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ex: 5,450'}),
    )
    valor_unitario = CommaDecimalField(
        max_digits=10, decimal_places=4, required=False,
        label="Custo unitário da compra (R$) — só para Entrada / Abertura",
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ex: 65,50'}),
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
