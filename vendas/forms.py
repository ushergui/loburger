from django import forms
from .models import CanalVenda
from produtos.forms import ThemeFormMixin

class CanalVendaForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = CanalVenda
        fields = ['nome', 'taxa_comissao', 'taxa_fixa', 'dias_repasse']
        widgets = {
            'taxa_comissao': forms.NumberInput(attrs={'step': '0.0001', 'placeholder': 'Ex: 0.12 para 12%'}),
        }
