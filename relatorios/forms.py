from django import forms
from .models import Despesa, DespesaRecorrente

class ThemeFormMixin:
    # Mixin para injetar estilos Tailwind / Hextech nos campos automaticamente
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'h-4 w-4 rounded border-hex_gold/30 bg-hex_dark_bg text-hex_blue focus:ring-hex_blue focus:ring-offset-hex_dark_bg'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2.5 px-3 text-hex_gold_light focus:outline-none focus:border-hex_blue transition-all'
                })
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2.5 px-3 text-hex_gold_light placeholder-hex_gold_light/30 focus:outline-none focus:border-hex_blue transition-all',
                    'rows': 3
                })
            else:
                field.widget.attrs.update({
                    'class': 'w-full bg-hex_dark_bg/80 border border-hex_gold/30 rounded py-2.5 px-3 text-hex_gold_light placeholder-hex_gold_light/30 focus:outline-none focus:border-hex_blue transition-all'
                })

class DespesaRecorrenteForm(ThemeFormMixin, forms.ModelForm):
    class Meta:
        model = DespesaRecorrente
        fields = ['descricao', 'categoria', 'valor_base', 'dia_vencimento', 'ativa']

class DespesaForm(ThemeFormMixin, forms.ModelForm):
    alterar_futuros = forms.BooleanField(
        required=False, 
        label="Atualizar este novo valor e data para os próximos meses",
        help_text="Marque para que as próximas despesas geradas automaticamente usem este novo valor e dia."
    )

    class Meta:
        model = Despesa
        fields = ['descricao', 'tipo', 'categoria', 'valor', 'status', 'data_vencimento', 'data_pagamento', 'observacao', 'alterar_futuros']
        widgets = {
            'data_vencimento': forms.DateInput(attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(attrs={'type': 'date'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.despesa_matriz:
            self.fields.pop('alterar_futuros')
