from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from .models import CanalVenda, TaxaFormaPagamento, FormaPagamento
from produtos.forms import ThemeFormMixin

class PercentageField(forms.DecimalField):
    def to_python(self, value):
        value = super().to_python(value)
        if value is not None:
            return value / Decimal('100.0')
        return value

    def prepare_value(self, value):
        val = super().prepare_value(value)
        if val is not None and val != '':
            try:
                dec = Decimal(str(val))
                return f"{dec * 100:.2f}".replace('.', ',')
            except:
                pass
        return val

class CanalVendaForm(ThemeFormMixin, forms.ModelForm):
    taxa_comissao = PercentageField(
        max_digits=5, 
        decimal_places=2, 
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 12,50 para 12.5%'}),
        label="Comissão Canal (%)"
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
        max_digits=5, 
        decimal_places=2, 
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 12,50'}),
        label="Comissão Específica (%)"
    )
    class Meta:
        model = TaxaFormaPagamento
        fields = ['forma_pagamento', 'taxa_comissao', 'taxa_fixa']
        widgets = {
            'taxa_fixa': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'R$ 0,00'}),
        }

TaxaFormaPagamentoFormSet = inlineformset_factory(
    CanalVenda,
    TaxaFormaPagamento,
    form=TaxaFormaPagamentoForm,
    extra=4,
    can_delete=True
)
