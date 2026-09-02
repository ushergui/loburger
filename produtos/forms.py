from decimal import Decimal
from django import forms
from core.utils import parse_numero_ptbr
from .models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal


class MoedaField(forms.DecimalField):
    """Campo de dinheiro que aceita o formato brasileiro (1.234,56)."""
    def to_python(self, value):
        if value in (None, '', 'None'):
            return Decimal('0.00')
        if isinstance(value, Decimal):
            return value
        return super().to_python(parse_numero_ptbr(value, Decimal('0.00')))

class ThemeFormMixin:
    # Mixin para injetar estilos Tailwind / Hextech nos campos automaticamente
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Verifica o tipo de widget para aplicar a estilização correta
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'h-4 w-4 rounded border-hex_gold/30 bg-hex_dark_bg text-hex_blue focus:ring-hex_blue focus:ring-offset-hex_dark_bg'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2 px-3 text-hex_gold_light focus:outline-none focus:border-hex_blue transition-all'
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2 px-3 text-hex_gold_light placeholder-hex_gold_light/30 focus:outline-none focus:border-hex_blue transition-all',
                    'rows': 3
                })
            else:
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2 px-3 text-hex_gold_light placeholder-hex_gold_light/30 focus:outline-none focus:border-hex_blue transition-all'
                })


class IngredienteForm(ThemeFormMixin, forms.ModelForm):
    estoque_minimo = MoedaField(
        required=False, label="Estoque mínimo (na unidade de consumo)",
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ex: 2000'}),
    )

    class Meta:
        model = Ingrediente
        fields = ['nome', 'unidade_medida', 'unidade_compra', 'fornecedor', 'estoque_minimo', 'categoria']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'nome' in self.fields:
            self.fields['nome'].widget.attrs.update({
                'oninput': "this.value = this.value.toUpperCase()",
                'style': "text-transform: uppercase;"
            })

    def clean_nome(self):
        nome = self.cleaned_data.get('nome')
        if nome:
            return nome.upper()
        return nome


class ProdutoForm(ThemeFormMixin, forms.ModelForm):
    custo_aquisicao = MoedaField(
        required=False, label="Custo de aquisição (revenda)",
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ex: 2,50'}),
    )

    class Meta:
        model = Produto
        fields = ['nome', 'categoria', 'descricao', 'foto', 'status', 'custo_aquisicao']


class FichaTecnicaItemForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = FichaTecnicaItem
        fields = ['ingrediente', 'produto_componente', 'quantidade']


class PrecoCanalForm(ThemeFormMixin, forms.ModelForm):
    preco = MoedaField(label="Preço no Canal (R$)",
                       widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ex: 44,00'}))

    class Meta:
        model = PrecoCanal
        fields = ['canal', 'preco']
