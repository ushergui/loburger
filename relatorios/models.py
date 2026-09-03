from django.db import models
from decimal import Decimal

CATEGORIA_CHOICES = (
    ('FORNECEDORES', 'Fornecedores / Insumos'),
    ('TAXA_PLATAFORMA', 'Taxa de Plataforma (iFood / UaiRango)'),
    ('TAXA_MAQUININHA', 'Taxa de Maquininha'),
    ('ENTREGA', 'Entregadores / Motoboy'),
    ('ENERGIA', 'Energia Elétrica (luz)'),
    ('AGUA_LUZ', 'Água / Esgoto'),
    ('INTERNET', 'Internet / Telefone'),
    ('IMPOSTOS', 'Impostos / Tributos (MEI / DAS)'),
    ('CONTADOR', 'Contador / Assessoria'),
    ('MANUTENCAO', 'Manutenção e Equipamentos'),
    ('VEICULO', 'Veículo / Moto (combustível, manutenção)'),
    ('GAS', 'Botijão de Gás'),
    ('MARKETING', 'Influencers / Marketing'),
    ('EMPRESTIMO', 'Empréstimos / Financiamentos'),
    ('LIMPEZA', 'Materiais de Limpeza'),
    ('FUNCIONARIOS', 'Funcionários / Pró-labore'),
    ('APLICATIVO', 'Aplicativo de Vendas Próprio'),
    ('RETIRADA_SOCIOS', 'Retirada dos Sócios'),
    ('OUTROS', 'Outros'),
)

# Categorias geradas automaticamente pelo sistema (não devem ser lançadas à mão)
CATEGORIAS_AUTOMATICAS = ('TAXA_PLATAFORMA', 'TAXA_MAQUININHA', 'ENTREGA', 'FORNECEDORES')

# Categorias que NÃO são custo da operação (não afetam a análise de preço do lanche),
# mas saem do caixa acumulado.
CATEGORIAS_NAO_OPERACIONAIS = ('RETIRADA_SOCIOS',)

# Categorias cujo gasto acompanha o movimento de vendas (custo variável).
# Todo o resto é tratado como custo fixo. Usado para classificar automaticamente,
# sem pedir isso ao usuário no formulário.
CATEGORIAS_VARIAVEIS = (
    'FORNECEDORES', 'TAXA_PLATAFORMA', 'TAXA_MAQUININHA', 'ENTREGA',
    'GAS', 'VEICULO', 'LIMPEZA', 'MARKETING',
)


def tipo_por_categoria(categoria):
    """'VARIAVEL' se o gasto acompanha o volume de vendas, senão 'FIXO'."""
    return 'VARIAVEL' if categoria in CATEGORIAS_VARIAVEIS else 'FIXO'

FREQUENCIA_CHOICES = (
    ('SEMANAL', 'Semanal (toda semana)'),
    ('QUINZENAL', 'Quinzenal (a cada 15 dias)'),
    ('MENSAL', 'Mensal (todo mês)'),
    ('BIMESTRAL', 'Bimestral (a cada 2 meses)'),
    ('TRIMESTRAL', 'Trimestral (a cada 3 meses)'),
    ('SEMESTRAL', 'Semestral (a cada 6 meses)'),
    ('ANUAL', 'Anual (uma vez por ano)'),
)

# Quantos meses um passo avança (frequências "de dias" tratadas à parte)
FREQUENCIA_MESES = {
    'MENSAL': 1, 'BIMESTRAL': 2, 'TRIMESTRAL': 3, 'SEMESTRAL': 6, 'ANUAL': 12,
}
FREQUENCIA_DIAS = {'SEMANAL': 7, 'QUINZENAL': 14}


def avancar_data(d, frequencia, passos=1):
    """A data `passos` intervalos à frente de `d`, respeitando a frequência.
    Meses: mantém o dia, ajustando para o último dia se o mês for menor."""
    import calendar as _cal
    from datetime import timedelta
    if frequencia in FREQUENCIA_DIAS:
        return d + timedelta(days=FREQUENCIA_DIAS[frequencia] * passos)
    meses = FREQUENCIA_MESES.get(frequencia, 1) * passos
    total = d.month - 1 + meses
    ano = d.year + total // 12
    mes = total % 12 + 1
    ultimo = _cal.monthrange(ano, mes)[1]
    return d.replace(year=ano, month=mes, day=min(d.day, ultimo))


class DespesaRecorrente(models.Model):
    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    credor = models.CharField(max_length=120, blank=True, default='', verbose_name="Fornecedor / Credor")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    frequencia = models.CharField(max_length=12, choices=FREQUENCIA_CHOICES, default='MENSAL', verbose_name="Frequência")
    primeiro_vencimento = models.DateField(null=True, blank=True, verbose_name="Primeiro Vencimento")
    dia_vencimento = models.IntegerField(null=True, blank=True, verbose_name="Dia Padrão de Vencimento")
    valor_base = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Base Previsto (R$)")
    ativa = models.BooleanField(default=True, verbose_name="Ativa (Gerar futuras?)")

    class Meta:
        verbose_name = "Despesa Recorrente"
        verbose_name_plural = "Despesas Recorrentes"

    def __str__(self):
        return f"{self.descricao} ({self.get_frequencia_display()})"

    def proxima_data(self, d):
        """A data seguinte, a partir de `d`, respeitando a frequência."""
        return avancar_data(d, self.frequencia)


class Despesa(models.Model):
    TIPO_CHOICES = (
        ('FIXO', 'Custo Fixo'),
        ('VARIAVEL', 'Custo Variável'),
    )
    
    STATUS_CHOICES = (
        ('PREVISTO', 'Previsto'),
        ('PAGO', 'Pago'),
    )

    ORIGEM_CHOICES = (
        ('MANUAL', 'Lançamento manual'),
        ('RECORRENTE', 'Gerada por molde fixo'),
        ('ESTOQUE', 'Entrada de estoque'),
        ('FECHAMENTO', 'Fechamento diário'),
    )

    FORMA_PAGAMENTO_CHOICES = (
        ('AVISTA', 'À vista (dinheiro / pix / débito)'),
        ('CARTAO', 'Cartão de crédito'),
        ('BOLETO', 'Boleto'),
        ('OUTRO', 'Outro'),
    )

    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    credor = models.CharField(max_length=120, blank=True, default='', verbose_name="Fornecedor / Credor",
        help_text="Quem vai receber (ex: 'Enel', 'João Refrigeração', 'Contador Silva').")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='FIXO', verbose_name="Tipo de Custo")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor (R$)")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PREVISTO', verbose_name="Status")
    data_vencimento = models.DateField(verbose_name="Data de Vencimento / Previsão de Pagamento")
    data_pagamento = models.DateField(null=True, blank=True, verbose_name="Data de Pagamento (Real)")

    observacao = models.TextField(blank=True, null=True, verbose_name="Observações")

    origem = models.CharField(max_length=12, choices=ORIGEM_CHOICES, default='MANUAL', verbose_name="Origem do Lançamento")
    forma_pagamento = models.CharField(max_length=10, choices=FORMA_PAGAMENTO_CHOICES, default='OUTRO', verbose_name="Forma de pagamento")
    data_referencia = models.DateField(null=True, blank=True, verbose_name="Dia de referência",
        help_text="Dia ao qual a despesa automática se refere (fechamento / entrada de estoque).")

    # Compra pelo carrinho "Registrar Compra" — liga a despesa às movimentações da nota
    grupo_compra = models.CharField(max_length=32, blank=True, default='', verbose_name="Grupo da compra")

    # Parcelamento (compra em Nx)
    grupo_parcelas = models.CharField(max_length=32, blank=True, default='', verbose_name="Grupo de parcelamento")
    parcela_num = models.PositiveIntegerField(default=1, verbose_name="Nº da parcela")
    parcela_total = models.PositiveIntegerField(default=1, verbose_name="Total de parcelas")

    despesa_matriz = models.ForeignKey(DespesaRecorrente, on_delete=models.SET_NULL, null=True, blank=True, related_name='faturas_geradas', verbose_name="Molde Gerador")

    @property
    def eh_parcelada(self):
        return self.parcela_total > 1

    class Meta:
        verbose_name = "Despesa / Custo"
        verbose_name_plural = "Despesas / Custos"
        ordering = ['-data_vencimento', 'descricao']

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.get_categoria_display()})"
