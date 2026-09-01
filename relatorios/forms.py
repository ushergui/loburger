from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import Despesa, DespesaRecorrente, CATEGORIA_CHOICES, CATEGORIAS_AUTOMATICAS

CATEGORIAS_MANUAIS = [(v, l) for v, l in CATEGORIA_CHOICES if v not in CATEGORIAS_AUTOMATICAS]

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

class MoneyDecimalField(forms.DecimalField):
    def to_python(self, value):
        if value in (None, '', 'None'):
            return None
        if isinstance(value, Decimal):
            return value
        clean_val = str(value).replace('R$', '').replace(' ', '').replace(',', '.').strip()
        return super().to_python(clean_val)

class DespesaRecorrenteForm(ThemeFormMixin, forms.ModelForm):
    valor_base = MoneyDecimalField(
        max_digits=10, 
        decimal_places=2, 
        label="Valor Base Previsto (R$)",
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 425,00'})
    )

    class Meta:
        model = DespesaRecorrente
        fields = ['descricao', 'credor', 'categoria', 'valor_base', 'dia_vencimento', 'ativa']
        widgets = {
            'credor': forms.TextInput(attrs={'placeholder': 'Ex: Enel, Sabesp, Vivo, Contador Silva'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'categoria' in self.fields:
            self.fields['categoria'].choices = list(CATEGORIAS_MANUAIS)

class DespesaForm(ThemeFormMixin, forms.ModelForm):
    valor = MoneyDecimalField(
        max_digits=10, 
        decimal_places=2, 
        label="Valor (R$)",
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 425,00'})
    )
    
    alterar_futuros = forms.BooleanField(
        required=False,
        label="Atualizar este novo valor e data para os próximos meses",
        help_text="Marque para que as próximas despesas geradas automaticamente usem este novo valor e dia."
    )

    parcelas = forms.IntegerField(
        required=False, min_value=1, max_value=60, initial=1,
        label="Parcelas",
        help_text="Deixe 1 para pagamento único. Para uma compra em Nx, o valor acima é o TOTAL — o sistema divide em N contas previstas, uma por mês.",
        widget=forms.NumberInput(attrs={'min': 1, 'max': 60}),
    )

    class Meta:
        model = Despesa
        fields = ['descricao', 'credor', 'tipo', 'categoria', 'valor', 'status', 'data_vencimento', 'data_pagamento', 'observacao', 'alterar_futuros']
        widgets = {
            'credor': forms.TextInput(attrs={'placeholder': 'Ex: João Refrigeração'}),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Categorias automáticas (taxas, motoboy, compras de estoque) não são lançadas à mão
        if 'categoria' in self.fields:
            atual = getattr(self.instance, 'categoria', None)
            choices = list(CATEGORIAS_MANUAIS)
            if atual and atual not in dict(choices):
                choices.append((atual, dict(CATEGORIA_CHOICES).get(atual, atual)))
            self.fields['categoria'].choices = choices
        if not self.instance or not self.instance.despesa_matriz:
            self.fields.pop('alterar_futuros', None)
        # Parcelamento só na criação (não na edição de uma despesa existente)
        if self.instance and self.instance.pk:
            self.fields.pop('parcelas', None)

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        data_pagamento = cleaned_data.get('data_pagamento')
        
        # Se informou data de pagamento, garante que o status fique como PAGO
        if data_pagamento and status != 'PAGO':
            cleaned_data['status'] = 'PAGO'
            
        # Se marcou como PAGO e não informou data, define hoje como data de pagamento
        if status == 'PAGO' and not data_pagamento:
            cleaned_data['data_pagamento'] = timezone.localdate()
            
        return cleaned_data

