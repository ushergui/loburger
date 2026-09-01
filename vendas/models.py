from django.db import models
from decimal import Decimal
from django.db.models import Sum

class FormaPagamento(models.Model):
    nome = models.CharField(max_length=50, unique=True, verbose_name="Nome da Forma de Pagamento")
    
    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        ordering = ['nome']
        
    def __str__(self):
        return self.nome

class CanalVenda(models.Model):
    nome = models.CharField(max_length=50, unique=True, verbose_name="Nome do Canal")
    taxa_comissao = models.DecimalField(max_digits=5, decimal_places=4, default=0, verbose_name="Taxa de Comissão (%)")
    taxa_fixa = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Taxa Fixa por Pedido (R$)")
    dias_repasse = models.IntegerField(default=1, verbose_name="Dias para Repasse")

    class Meta:
        verbose_name = "Canal de Venda"
        verbose_name_plural = "Canais de Venda"
        ordering = ['nome']

    def __str__(self):
        # Mostra o nome do canal e suas taxas de forma limpa
        taxa_pct = (self.taxa_comissao * 100).quantize(Decimal('0.01'))
        return f"{self.nome} (Taxa: {taxa_pct}% + R$ {self.taxa_fixa})"


class TaxaFormaPagamento(models.Model):

    canal = models.ForeignKey(CanalVenda, on_delete=models.CASCADE, related_name='taxas_pagamento', verbose_name="Canal de Venda")
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Forma de Pagamento")
    taxa_comissao = models.DecimalField(max_digits=5, decimal_places=4, default=0, verbose_name="Taxa (%)")
    taxa_fixa = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Taxa Fixa (R$)")

    class Meta:
        verbose_name = "Taxa por Forma de Pagamento"
        verbose_name_plural = "Taxas por Forma de Pagamento"
        unique_together = ('canal', 'forma_pagamento')

    def __str__(self):
        taxa_pct = (self.taxa_comissao * 100).quantize(Decimal('0.01'))
        return f"{self.canal.nome} - {self.forma_pagamento.nome}: {taxa_pct}%"


class Pedido(models.Model):
    STATUS_CHOICES = (
        ('RECEBIDO', 'Recebido'),
        ('PREPARO', 'Em Preparo'),
        ('CONCLUIDO', 'Concluído'),
        ('CANCELADO', 'Cancelado'),
    )

    cliente_nome = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nome do Cliente")
    canal = models.ForeignKey(CanalVenda, on_delete=models.PROTECT, related_name='pedidos', verbose_name="Canal de Venda")
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Forma de Pagamento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RECEBIDO', verbose_name="Status do Pedido")
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    
    # Valores financeiros calculados automaticamente
    valor_bruto = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Valor Bruto (R$)")
    taxas_canal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Taxas do App/Canal (R$)")
    taxas_pagamento = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Taxas de Pagamento/Cartão (R$)")
    custo_ingredientes = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Custo de Produção (R$)")
    lucro_liquido = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Lucro Líquido Real (R$)")
    desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Desconto Concedido (R$)")
    
    # Flag para controle de baixa de estoque e evitar duplicidade
    estoque_baixado = models.BooleanField(default=False, verbose_name="Baixa de Estoque Realizada")

    class Meta:
        verbose_name = "Pedido / Venda"
        verbose_name_plural = "Pedidos / Vendas"
        ordering = ['-data_criacao']

    def __str__(self):
        # Exibição básica do pedido
        data_formatada = self.data_criacao.strftime('%d/%m %H:%M') if self.data_criacao else 'Pendente'
        return f"Pedido #{self.id} - {self.canal.nome} ({data_formatada})"

    def recalcular_valores_financeiros(self, save=True):
        # Lógica de Negócio: Calcula automaticamente todo o financeiro do pedido
        # com base nos itens cadastrados.
        itens = self.itens.all()
        
        # 1. Valor Bruto
        bruto = sum(item.quantidade * item.preco_unitario for item in itens)
        self.valor_bruto = Decimal(bruto).quantize(Decimal('0.01'))
        
        if self.status != 'CANCELADO' and self.valor_bruto > 0:
            # 2. Taxas do Canal (App, etc)
            taxas = (self.valor_bruto * self.canal.taxa_comissao) + self.canal.taxa_fixa
            self.taxas_canal = Decimal(taxas).quantize(Decimal('0.01'))
            
            # 2.1 Taxas de Pagamento (Cartão, Maquininha, etc)
            if self.forma_pagamento:
                taxa_pgto = TaxaFormaPagamento.objects.filter(canal=self.canal, forma_pagamento=self.forma_pagamento).first()
                if taxa_pgto:
                    calc_taxa_pgto = (self.valor_bruto * taxa_pgto.taxa_comissao) + taxa_pgto.taxa_fixa
                    self.taxas_pagamento = Decimal(calc_taxa_pgto).quantize(Decimal('0.01'))
                else:
                    self.taxas_pagamento = Decimal('0.00')
            else:
                self.taxas_pagamento = Decimal('0.00')
        else:
            self.taxas_canal = Decimal('0.00')
            self.taxas_pagamento = Decimal('0.00')

        # 3. Custo total dos ingredientes pela ficha técnica (CMV - Custo da Mercadoria Vendida)
        # Calculado com base no custo_unitario atualizado na entrada do estoque (custo médio ponderado)
        custo = sum(item.quantidade * item.produto.custo_total for item in itens)
        self.custo_ingredientes = Decimal(custo).quantize(Decimal('0.01'))

        # 4. Lucro Líquido Real = Faturamento Bruto - Taxas do Canal - Taxas de Pagamento - CMV
        # O custo dos ingredientes reflete o preço de compra lançado na entrada do estoque.
        # Nota: as Despesas de categoria FORNECEDORES (geradas na entrada do estoque) NÃO
        # devem ser subtraídas novamente no dashboard para evitar dupla contagem.
        self.lucro_liquido = (self.valor_bruto - self.taxas_canal - self.taxas_pagamento - self.custo_ingredientes).quantize(Decimal('0.01'))

        if save:
            # Salvamos apenas os campos necessários para evitar recursão
            Pedido.objects.filter(id=self.id).update(
                valor_bruto=self.valor_bruto,
                taxas_canal=self.taxas_canal,
                taxas_pagamento=self.taxas_pagamento,
                custo_ingredientes=self.custo_ingredientes,
                lucro_liquido=self.lucro_liquido
            )

    def processar_baixa_estoque(self, responsavel=None):
        # Lógica de Negócio: Efetua a baixa física de insumos no estoque.
        # Roda quando o pedido sai do status Cancelado/Pendente para ativo.
        from estoque.models import MovimentacaoEstoque
        
        if self.estoque_baixado or self.status == 'CANCELADO':
            return

        itens = self.itens.all()
        if not itens.exists():
            return

        for item in itens:
            produto = item.produto
            # Percorre a ficha técnica do produto
            for ficha in produto.ficha_tecnica.all():
                quantidade_deduzir = ficha.quantidade * item.quantidade
                
                # Desconta diretamente no estoque atual do ingrediente
                ingrediente = ficha.ingrediente
                ingrediente.estoque_atual -= quantidade_deduzir
                ingrediente.save()
                
                # Cria a movimentação de histórico
                MovimentacaoEstoque.objects.create(
                    ingrediente=ingrediente,
                    quantidade=quantidade_deduzir,
                    tipo='SAIDA_VENDA',
                    observacao=f"Baixa automática pelo Pedido #{self.id}",
                    responsavel=responsavel
                )
        
        self.estoque_baixado = True
        Pedido.objects.filter(id=self.id).update(estoque_baixado=True)

    def estornar_estoque(self, responsavel=None):
        # Lógica de Negócio: Devolve os itens ao estoque se o pedido for cancelado.
        from estoque.models import MovimentacaoEstoque
        
        if not self.estoque_baixado:
            return
            
        for item in self.itens.all():
            produto = item.produto
            for ficha in produto.ficha_tecnica.all():
                quantidade_estornar = ficha.quantidade * item.quantidade
                
                # Devolve ao estoque atual do ingrediente
                ingrediente = ficha.ingrediente
                ingrediente.estoque_atual += quantidade_estornar
                ingrediente.save()
                
                # Cria a movimentação de histórico de entrada
                MovimentacaoEstoque.objects.create(
                    ingrediente=ingrediente,
                    quantidade=quantidade_estornar,
                    tipo='AJUSTE',
                    observacao=f"Estorno por cancelamento do Pedido #{self.id}",
                    responsavel=responsavel
                )
                
        self.estoque_baixado = False
        Pedido.objects.filter(id=self.id).update(estoque_baixado=False)


class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens', verbose_name="Pedido")
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, verbose_name="Produto")
    quantidade = models.PositiveIntegerField(default=1, verbose_name="Quantidade")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário (R$)")

    class Meta:
        verbose_name = "Item de Pedido"
        verbose_name_plural = "Itens de Pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome} no Pedido #{self.pedido.id}"

    @property
    def valor_total(self):
        return (self.quantidade * self.preco_unitario).quantize(Decimal('0.01'))


# Signals para automação de baixa de estoque e auditoria
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Pedido)
def gerenciar_estoque_pedido(sender, instance, created, **kwargs):
    # Lógica de Negócio: Efetua baixa se o pedido não estiver cancelado.
    # Se o status for cancelado e o estoque já tiver sido deduzido, estorna.
    if instance.status != 'CANCELADO':
        if not instance.estoque_baixado:
            # Processa baixa para os insumos e gera histórico
            instance.processar_baixa_estoque()
    else:
        if instance.estoque_baixado:
            # Devolve ao estoque e gera histórico de ajuste
            instance.estornar_estoque()

class FechamentoDiarioInfo(models.Model):
    data = models.DateField(unique=True, verbose_name="Data do Fechamento")
    quantidade_entregas = models.PositiveIntegerField(default=0, verbose_name="Quantidade de Entregas")
    taxa_entrega = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('9.00'), verbose_name="Taxa de Entrega (R$)")
    
    class Meta:
        verbose_name = "Informação do Fechamento Diário"
        verbose_name_plural = "Informações dos Fechamentos Diários"
        
    def __str__(self):
        return f"Fechamento {self.data.strftime('%d/%m/%Y')} - {self.quantidade_entregas} entregas"

