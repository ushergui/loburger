from django import forms
from .models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal

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
    class Meta:
        model = Produto
        fields = ['nome', 'categoria', 'descricao', 'foto', 'status']


class FichaTecnicaItemForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = FichaTecnicaItem
        fields = ['ingrediente', 'quantidade']


class PrecoCanalForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = PrecoCanal
        fields = ['canal', 'preco']
