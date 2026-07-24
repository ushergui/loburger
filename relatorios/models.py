from django.db import models
from decimal import Decimal

class Despesa(models.Model):
    TIPO_CHOICES = (
        ('FIXO', 'Custo Fixo'),
        ('VARIAVEL', 'Custo Variável'),
    )
    
    CATEGORIA_CHOICES = (
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

    descricao = models.CharField(max_length=150, verbose_name="Descrição da Despesa")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='FIXO', verbose_name="Tipo de Custo")
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='OUTROS', verbose_name="Categoria")
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor (R$)")
    data_pagamento = models.DateField(verbose_name="Data de Vencimento/Pagamento")
    observacao = models.TextField(blank=True, null=True, verbose_name="Observações")

    class Meta:
        verbose_name = "Despesa / Custo"
        verbose_name_plural = "Despesas / Custos"
        ordering = ['-data_pagamento', 'descricao']

    def __str__(self):
        return f"{self.descricao} - R$ {self.valor} ({self.get_categoria_display()})"
