from django.db import models
from decimal import Decimal
from django.db.models import Sum


class ConfiguracaoFinanceira(models.Model):
    """Parâmetros financeiros globais, editáveis pela Gestão. Registro único (pk=1)."""
    taxa_maquininha = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal('0.0350'),
        verbose_name="Taxa da maquininha na entrega (%)",
        help_text="Ex: 0.035 para 3,5%. Aplicada quando o cliente paga no cartão/pix da maquininha do Igor na entrega.")
    taxa_entrega = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('9.00'),
        verbose_name="Valor da entrega (R$)",
        help_text="Valor fixo cobrado do cliente e repassado ao entregador por entrega.")
    caixa_inicial = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        verbose_name="Saldo de caixa inicial (R$)",
        help_text="Dinheiro que já existia no caixa no dia em que o sistema começou a ser usado.")
    ultima_geracao_recorrentes = models.DateField(
        null=True, blank=True, verbose_name="Última geração de contas recorrentes",
        help_text="Controle interno: as faturas dos moldes fixos são geradas no máximo 1x por dia.")

    class Meta:
        verbose_name = "Configuração Financeira"
        verbose_name_plural = "Configuração Financeira"

    def __str__(self):
        return "Configuração Financeira"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Entregador(models.Model):
    nome = models.CharField(max_length=80, unique=True, verbose_name="Nome do Entregador")
    eh_socio = models.BooleanField(
        default=False, verbose_name="É sócio (Igor / esposa)",
        help_text="Se marcado, as entregas feitas por esta pessoa NÃO geram custo de motoboy — o valor fica na empresa.")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Entregador"
        verbose_name_plural = "Entregadores"
        ordering = ['nome']

    def __str__(self):
        return self.nome + (" (sócio)" if self.eh_socio else "")


class EntregaDiaria(models.Model):
    data = models.DateField(verbose_name="Data")
    entregador = models.ForeignKey(Entregador, on_delete=models.PROTECT, related_name='entregas', verbose_name="Entregador")
    quantidade = models.PositiveIntegerField(default=0, verbose_name="Quantidade de Entregas")

    class Meta:
        verbose_name = "Entrega do Dia"
        verbose_name_plural = "Entregas do Dia"
        unique_together = ('data', 'entregador')
        ordering = ['-data', 'entregador__nome']

    def __str__(self):
        return f"{self.data.strftime('%d/%m/%Y')} - {self.entregador.nome}: {self.quantidade}"

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
    taxa_comissao = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        verbose_name="Comissão base (%)",
        help_text="Cobrada quando o cliente paga na entrega. iFood 12%, UaiRango 8%, app próprio 0%.")
    taxa_online = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        verbose_name="Taxa total no pagamento on-line (%)",
        help_text="Cobrada quando o cliente paga dentro do app. iFood 15,2%, UaiRango 11,5%, app próprio 0%.")
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

    @property
    def taxa_comissao_pct(self):
        return (self.taxa_comissao * 100).quantize(Decimal('0.01'))

    @property
    def taxa_online_pct(self):
        return (self.taxa_online * 100).quantize(Decimal('0.01'))


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

    MODO_PAGAMENTO_CHOICES = (
        ('ONLINE', 'Pago no app da plataforma'),
        ('DINHEIRO', 'Dinheiro na entrega'),
        ('MAQUININHA', 'Maquininha na entrega'),
    )

    cliente_nome = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nome do Cliente")
    canal = models.ForeignKey(CanalVenda, on_delete=models.PROTECT, related_name='pedidos', verbose_name="Canal de Venda")
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Forma de Pagamento")
    modo_pagamento = models.CharField(max_length=12, choices=MODO_PAGAMENTO_CHOICES, default='ONLINE', verbose_name="Modo de Pagamento")
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
        # Lógica de Negócio: recalcula o financeiro do pedido com base nos itens.
        # REGIME DE CAIXA: o custo dos insumos NÃO entra aqui — ele é reconhecido
        # na compra (entrada de estoque gera Despesa FORNECEDORES). O custo_ingredientes
        # fica só como informativo para a margem de contribuição por lanche.
        itens = self.itens.all()

        # 1. Valor Bruto (o que o cliente pagou, incluindo o preço cheio do app)
        bruto = sum((item.quantidade * item.preco_unitario for item in itens), Decimal('0.00'))
        self.valor_bruto = Decimal(bruto).quantize(Decimal('0.01'))

        if self.status != 'CANCELADO' and self.valor_bruto > 0:
            config = ConfiguracaoFinanceira.get_solo()
            if self.modo_pagamento == 'ONLINE':
                # Pagamento dentro do app: a plataforma fica com a taxa total (iFood 15,2%, UaiRango 11,5%)
                self.taxas_canal = (self.valor_bruto * self.canal.taxa_online + self.canal.taxa_fixa).quantize(Decimal('0.01'))
                self.taxas_pagamento = Decimal('0.00')
            elif self.modo_pagamento == 'MAQUININHA':
                # Na entrega, no cartão/pix da maquininha do Igor: comissão base da plataforma + taxa da maquininha
                self.taxas_canal = (self.valor_bruto * self.canal.taxa_comissao + self.canal.taxa_fixa).quantize(Decimal('0.01'))
                self.taxas_pagamento = (self.valor_bruto * config.taxa_maquininha).quantize(Decimal('0.01'))
            else:  # DINHEIRO na entrega (ou pix direto): só a comissão base
                self.taxas_canal = (self.valor_bruto * self.canal.taxa_comissao + self.canal.taxa_fixa).quantize(Decimal('0.01'))
                self.taxas_pagamento = Decimal('0.00')
        else:
            self.taxas_canal = Decimal('0.00')
            self.taxas_pagamento = Decimal('0.00')

        # 4. CMV informativo (custo da ficha técnica pelo custo médio ponderado do insumo)
        custo = sum((item.quantidade * item.produto.custo_total for item in itens), Decimal('0.00'))
        self.custo_ingredientes = Decimal(custo).quantize(Decimal('0.01'))

        # 5. Valor líquido recebido = o que entra no caixa da operação nesta venda
        #    (faturamento bruto - comissão do canal - taxa de pagamento - desconto).
        self.lucro_liquido = (self.valor_bruto - self.taxas_canal - self.taxas_pagamento - self.desconto).quantize(Decimal('0.01'))

        if save:
            Pedido.objects.filter(id=self.id).update(
                valor_bruto=self.valor_bruto,
                taxas_canal=self.taxas_canal,
                taxas_pagamento=self.taxas_pagamento,
                custo_ingredientes=self.custo_ingredientes,
                lucro_liquido=self.lucro_liquido
            )

    @property
    def valor_liquido(self):
        # Alias legível: o que efetivamente entrou no caixa com esta venda.
        return self.lucro_liquido

    @property
    def margem_contribuicao(self):
        # Para engenharia de cardápio: sobra depois de taxas E custo de insumo.
        return (self.valor_bruto - self.taxas_canal - self.taxas_pagamento
                - self.custo_ingredientes - self.desconto).quantize(Decimal('0.01'))

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

