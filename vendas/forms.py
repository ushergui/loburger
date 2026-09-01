from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import CanalVenda, TaxaFormaPagamento, FormaPagamento
from produtos.forms import ThemeFormMixin

class CustomDecimalField(forms.DecimalField):
    def to_python(self, value):
        if value in (None, '', 'None'):
            return Decimal('0.00')
        if isinstance(value, Decimal):
            return value
        clean_val = str(value).replace(',', '.').strip()
        return super().to_python(clean_val)

class PercentageField(forms.Field):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', forms.TextInput(attrs={'placeholder': 'Ex: 8 para 8%'}))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in (None, '', 'None'):
            return Decimal('0.0000')
        if isinstance(value, Decimal):
            return value
        clean_val = str(value).replace('%', '').replace(',', '.').strip()
        try:
            val = Decimal(clean_val)
        except Exception:
            raise forms.ValidationError("Informe uma porcentagem válida (Ex: 8 ou 8,50).")
        
        # Converte porcentagem para decimal (Ex: 8 -> 0.0800)
        return (val / Decimal('100.0')).quantize(Decimal('0.0001'))

    def prepare_value(self, value):
        if value in (None, ''):
            return ''
        try:
            dec = Decimal(str(value))
            pct = (dec * Decimal('100.0')).quantize(Decimal('0.01'))
            if pct == pct.to_integral():
                return f"{pct:.0f}"
            return f"{pct:.2f}".replace('.', ',')
        except Exception:
            return value

class CanalVendaForm(ThemeFormMixin, forms.ModelForm):
    taxa_comissao = PercentageField(
        label="Comissão Canal (%)",
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 8 ou 12,50'}),
        help_text="Digite a porcentagem (Ex: 8 para 8%)"
    )
    taxa_fixa = CustomDecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False,
        label="Taxa Fixa por Pedido (R$)",
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 1,50 ou 0,00'})
    )
    class Meta:
        model = CanalVenda
        fields = ['nome', 'taxa_comissao', 'taxa_fixa', 'dias_repasse']

class FormaPagamentoForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = FormaPagamento
        fields = ['nome']
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex: Pix, Sodexo, VR, Vale Alimentação'}),
        }

class TaxaFormaPagamentoForm(ThemeFormMixin, forms.ModelForm):
    taxa_comissao = PercentageField(
        label="Comissão Específica (%)",
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 2,50'})
    )
    taxa_fixa = CustomDecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        label="Taxa Fixa (R$)",
        widget=forms.TextInput(attrs={'placeholder': '0,00'})
    )
    class Meta:
        model = TaxaFormaPagamento
        fields = ['forma_pagamento', 'taxa_comissao', 'taxa_fixa']

TaxaFormaPagamentoFormSet = inlineformset_factory(
    CanalVenda,
    TaxaFormaPagamento,
    form=TaxaFormaPagamentoForm,
    extra=4,
    can_delete=True
)
