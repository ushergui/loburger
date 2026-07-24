from django import forms
from .models import MovimentacaoEstoque
from produtos.forms import ThemeFormMixin

class MovimentacaoEstoqueForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = MovimentacaoEstoque
        fields = ['ingrediente', 'quantidade', 'tipo', 'valor_unitario', 'observacao']
        widgets = {
            'tipo': forms.Select(choices=(
                ('ENTRADA', 'Entrada (Compra / Reposição)'),
                ('SAIDA_PERDA', 'Saída por Perda / Descarte'),
                ('AJUSTE', 'Ajuste Geral de Inventário'),
            ))
        }
