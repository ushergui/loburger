from django.db import models
from decimal import Decimal

CATEGORIA_CHOICES = (
    ('FORNECEDORES', 'Fornecedores / Insumos'),
    ('ENERGIA', 'Energia'),
    ('AGUA_LUZ', 'Água / Luz'),
    ('INTERNET', 'Internet / Telefone'),
    ('IMPOSTOS', 'Impostos / Tributos'),
    ('CONTADOR', 'Contador / Assessoria'),
    ('MANUTENCAO', 'Manutenção e Equipamentos'),
    ('GAS', 'Botijão de Gás'),
    ('MARKETING', 'Influencers / Marketing'),
    ('EMPRESTIMO', 'Empréstimos / Financiamentos'),
    ('LIMPEZA', 'Materiais de Limpeza'),
    ('FUNCIONARIOS', 'Funcionários / Pró-labore'),
    ('AUTOCONSUMO', 'Auto consumo de lanches'),
    ('APLICATIVO', 'Aplicativo de Vendas Próprio'),
    ('OUTROS', 'Outros'),
)

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

    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='FIXO', verbose_name="Tipo de Custo")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor (R$)")
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PREVISTO', verbose_name="Status")
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")
    data_pagamento = models.DateField(null=True, blank=True, verbose_name="Data de Pagamento (Real)")
    
    observacao = models.TextField(blank=True, null=True, verbose_name="Observações")
    
    despesa_matriz = models.ForeignKey(DespesaRecorrente, on_delete=models.SET_NULL, null=True, blank=True, related_name='faturas_geradas', verbose_name="Molde Gerador")

    class Meta:
        verbose_name = "Despesa / Custo"
        verbose_name_plural = "Despesas / Custos"
        ordering = ['-data_vencimento', 'descricao']

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.get_categoria_display()})"
