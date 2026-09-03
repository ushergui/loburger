from django.db import models
from django.conf import settings

class MovimentacaoEstoque(models.Model):
    TIPOS_MOVIMENTACAO = (
        ('ENTRADA', 'Entrada (Compra / Reposição)'),
        ('ABERTURA', 'Carga Inicial / Abertura'),
        ('SAIDA_VENDA', 'Saída Automática (Venda)'),
        ('SAIDA_PERDA', 'Saída por Perda / Descarte'),
        ('SAIDA_AUTOCONSUMO', 'Saída por Autoconsumo'),
        ('AJUSTE', 'Ajuste de Inventário'),
    )

    ingrediente = models.ForeignKey('produtos.Ingrediente', on_delete=models.CASCADE, related_name='movimentacoes', verbose_name="Ingrediente / Insumo")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3, verbose_name="Quantidade")
    tipo = models.CharField(max_length=20, choices=TIPOS_MOVIMENTACAO, verbose_name="Tipo de Movimentação")
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="Custo Unitário da Compra (R$)")
    data_movimentacao = models.DateTimeField(auto_now_add=True, verbose_name="Data / Hora")
    observacao = models.TextField(blank=True, null=True, verbose_name="Observações / Justificativa")
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Responsável")

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"
        ordering = ['-data_movimentacao']

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.quantidade} {self.ingrediente.unidade_medida} de {self.ingrediente.nome}"

    @property
    def valor_movimento(self):
        # Valor financeiro da movimentação, pelo custo (informado na entrada ou custo médio atual).
        from decimal import Decimal
        custo = self.valor_unitario if self.valor_unitario else self.ingrediente.custo_unitario
        return (self.quantidade * (custo or Decimal('0'))).quantize(Decimal('0.01'))

