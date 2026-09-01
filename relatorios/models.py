from django.db import models
from decimal import Decimal

CATEGORIA_CHOICES = (
    ('FORNECEDORES', 'Fornecedores / Insumos'),
    ('TAXA_PLATAFORMA', 'Taxa de Plataforma (iFood / UaiRango)'),
    ('TAXA_MAQUININHA', 'Taxa de Maquininha'),
    ('ENTREGA', 'Entregadores / Motoboy'),
    ('ENERGIA', 'Energia'),
    ('AGUA_LUZ', 'Água / Luz'),
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

class DespesaRecorrente(models.Model):
    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    dia_vencimento = models.IntegerField(verbose_name="Dia Padrão de Vencimento")
    valor_base = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Base Previsto (R$)")
    ativa = models.BooleanField(default=True, verbose_name="Ativa (Gerar futuras?)")
    
    class Meta:
        verbose_name = "Despesa Fixa (Molde)"
        verbose_name_plural = "Despesas Fixas (Moldes)"
        
    def __str__(self):
        return f"{self.descricao} (Dia {self.dia_vencimento})"


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

    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='FIXO', verbose_name="Tipo de Custo")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor (R$)")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PREVISTO', verbose_name="Status")
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")
    data_pagamento = models.DateField(null=True, blank=True, verbose_name="Data de Pagamento (Real)")

    observacao = models.TextField(blank=True, null=True, verbose_name="Observações")

    origem = models.CharField(max_length=12, choices=ORIGEM_CHOICES, default='MANUAL', verbose_name="Origem do Lançamento")
    data_referencia = models.DateField(null=True, blank=True, verbose_name="Dia de referência",
        help_text="Dia ao qual a despesa automática se refere (fechamento / entrada de estoque).")

    despesa_matriz = models.ForeignKey(DespesaRecorrente, on_delete=models.SET_NULL, null=True, blank=True, related_name='faturas_geradas', verbose_name="Molde Gerador")

    class Meta:
        verbose_name = "Despesa / Custo"
        verbose_name_plural = "Despesas / Custos"
        ordering = ['-data_vencimento', 'descricao']

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.get_categoria_display()})"
