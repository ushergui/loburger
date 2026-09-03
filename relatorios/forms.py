from decimal import Decimal
from django import forms
from django.utils import timezone
from core.utils import parse_numero_ptbr
from .models import (
    Despesa, DespesaRecorrente, CATEGORIA_CHOICES, CATEGORIAS_AUTOMATICAS,
    tipo_por_categoria,
)

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
        return super().to_python(parse_numero_ptbr(value))

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

    # Em vez do dropdown de status: uma decisão simples e explícita.
    ja_paga = forms.BooleanField(
        required=False,
        label="Já paguei esta despesa",
        help_text="Deixe DESMARCADO se ainda vai pagar: a conta entra em "
                  "\"Contas a Pagar\" e você confirma o pagamento no dia certo "
                  "pelo botão Pagar. Marque só se o dinheiro já saiu.",
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
        # 'tipo' (fixo/variável) sai do formulário — é deduzido da categoria.
        # 'status' também sai — é decidido pelo checkbox "já paguei".
        fields = ['descricao', 'credor', 'categoria', 'valor', 'data_vencimento', 'data_pagamento', 'observacao', 'alterar_futuros']
        widgets = {
            'credor': forms.TextInput(attrs={'placeholder': 'Ex: João Refrigeração'}),
            'data_vencimento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }
        labels = {
            'data_vencimento': "Data de vencimento / previsão de pagamento",
            'data_pagamento': "Data em que foi paga",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_pagamento'].required = False
        # Categorias automáticas (taxas, motoboy, compras de estoque) não são lançadas à mão
        if 'categoria' in self.fields:
            atual = getattr(self.instance, 'categoria', None)
            choices = list(CATEGORIAS_MANUAIS)
            if atual and atual not in dict(choices):
                choices.append((atual, dict(CATEGORIA_CHOICES).get(atual, atual)))
            self.fields['categoria'].choices = choices
        # Ao editar uma despesa já paga, o checkbox já vem marcado
        if self.instance and self.instance.pk and self.instance.status == 'PAGO':
            self.fields['ja_paga'].initial = True
        if not self.instance or not self.instance.despesa_matriz:
            self.fields.pop('alterar_futuros', None)
        # Parcelamento só na criação (não na edição de uma despesa existente)
        if self.instance and self.instance.pk:
            self.fields.pop('parcelas', None)

    def clean(self):
        cleaned_data = super().clean()
        ja_paga = cleaned_data.get('ja_paga')
        data_pagamento = cleaned_data.get('data_pagamento')

        if ja_paga:
            cleaned_data['status'] = 'PAGO'
            cleaned_data['data_pagamento'] = data_pagamento or timezone.localdate()
        else:
            # Ainda não foi paga: nunca vai para o histórico de pagas
            cleaned_data['status'] = 'PREVISTO'
            cleaned_data['data_pagamento'] = None

        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.status = self.cleaned_data['status']
        obj.data_pagamento = self.cleaned_data['data_pagamento']
        obj.tipo = tipo_por_categoria(self.cleaned_data.get('categoria'))
        if commit:
            obj.save()
        return obj

