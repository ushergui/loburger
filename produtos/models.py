from django.db import models
from decimal import Decimal

class Ingrediente(models.Model):
    UNIDADES_MEDIDA = (
        ('kg', 'Quilograma (kg)'),
        ('g', 'Grama (g)'),
        ('l', 'Litro (l)'),
        ('ml', 'Mililitro (ml)'),
        ('un', 'Unidade (un)'),
    )
    CATEGORIAS = (
        ('PROTEINA', 'Proteínas'),
        ('PAO', 'Pães'),
        ('MOLHO', 'Molhos'),
        ('VEGETAL', 'Vegetais / Saladas'),
        ('QUEIJO', 'Queijos'),
        ('EMBALAGEM', 'Embalagens'),
        ('OUTROS', 'Outros'),
    )

    nome = models.CharField(max_length=100, verbose_name="Nome do Insumo")
    unidade_medida = models.CharField(max_length=5, choices=UNIDADES_MEDIDA, default='g', verbose_name="Unidade de Medida")
    unidade_compra = models.CharField(max_length=5, choices=UNIDADES_MEDIDA, default='g', verbose_name="Unidade de Compra (Entrada)")
    custo_unitario = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0.0000'), verbose_name="Custo Unitário (R$)")
    fornecedor = models.CharField(max_length=100, blank=True, null=True, verbose_name="Fornecedor")
    estoque_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Mínimo")
    estoque_atual = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estoque Atual")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='OUTROS', verbose_name="Categoria")

    class Meta:
        verbose_name = "Ingrediente / Insumo"
        verbose_name_plural = "Ingredientes / Insumos"
        ordering = ['nome']

    def __str__(self):
        return f"{self.nome} ({self.get_unidade_medida_display()})"

    @property
    def status_estoque(self):
        # Retorna o status baseado nos limites mínimo e atual
        if self.estoque_atual <= 0:
            return 'CRITICO'
        elif self.estoque_atual < self.estoque_minimo:
            return 'BAIXO'
        else:
            return 'OK'
    @property
    def obter_fator_conversao(self):
        # Lógica de Negócio: Fator de conversão automático de unidades de compra para consumo
        if self.unidade_compra == 'kg' and self.unidade_medida == 'g':
            return Decimal('1000.00')
        elif self.unidade_compra == 'l' and self.unidade_medida == 'ml':
            return Decimal('1000.00')
        return Decimal('1.00')


class Produto(models.Model):
    CATEGORIAS = (
        ('BURGER', 'Hambúrgueres (Campeões)'),
        ('BEBIDA', 'Bebidas'),
        ('ACOMPANHAMENTO', 'Acompanhamentos e Fritas'),
        ('COMBO', 'Combos Hextech'),
        ('ENTRADA', 'Entradas e Porções'),
        ('CROISSANT', 'Croissants'),
        ('SOBREMESA', 'Sobremesas e Mimos'),
    )

    nome = models.CharField(max_length=100, verbose_name="Nome do Produto")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='BURGER', verbose_name="Categoria")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição do Lanche")
    foto = models.ImageField(upload_to='produtos/', blank=True, null=True, verbose_name="Foto do Lanche")
    status = models.BooleanField(default=True, verbose_name="Ativo / Em Linha")

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['nome']

    def __str__(self):
        return self.nome

    @property
    def custo_total(self):
        # Lógica de Negócio: Calcula o custo de produção somando cada item da Ficha Técnica
        itens = self.ficha_tecnica.all()
        custo = Decimal('0.00')
        for item in itens:
            custo += item.quantidade * item.ingrediente.custo_unitario
        return custo.quantize(Decimal('0.01'))


class FichaTecnicaItem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='ficha_tecnica', verbose_name="Produto")
    ingrediente = models.ForeignKey(Ingrediente, on_delete=models.CASCADE, verbose_name="Ingrediente / Insumo")
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantidade Utilizada")

    class Meta:
        verbose_name = "Item de Ficha Técnica"
        verbose_name_plural = "Itens de Ficha Técnica"
        unique_together = ('produto', 'ingrediente')

    def __str__(self):
        return f"{self.quantidade} {self.ingrediente.unidade_medida} of {self.ingrediente.nome} em {self.produto.nome}"

    @property
    def custo_item(self):
        # Lógica de Negócio: Custo específico desse ingrediente na receita
        return (self.quantidade * self.ingrediente.custo_unitario).quantize(Decimal('0.01'))


class PrecoCanal(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='precos_canais', verbose_name="Produto")
    # Referência preguiçosa a vendas.CanalVenda para evitar imports circulares
    canal = models.ForeignKey('vendas.CanalVenda', on_delete=models.CASCADE, related_name='precos_produtos', verbose_name="Canal de Venda")
    preco = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço no Canal (R$)")

    class Meta:
        verbose_name = "Preço por Canal"
        verbose_name_plural = "Preços por Canal"
        unique_together = ('produto', 'canal')

    def __str__(self):
        return f"{self.produto.nome} no {self.canal.nome}: R$ {self.preco}"

    @property
    def taxa_valor(self):
        # Lógica de Negócio: Calcula o valor da comissão absoluta cobrada pelo canal
        return (self.preco * self.canal.taxa_comissao + self.canal.taxa_fixa).quantize(Decimal('0.01'))

    @property
    def lucro_liquido(self):
        # Lógica de Negócio: Lucro Líquido = Preço - Taxa Canal - Custo de Insumos
        return (self.preco - self.taxa_valor - self.produto.custo_total).quantize(Decimal('0.01'))

    @property
    def margem_lucro_pct(self):
        # Lógica de Negócio: Percentual de lucro sobre o preço de venda no canal
        if self.preco <= 0:
            return Decimal('0.00')
        return ((self.lucro_liquido / self.preco) * 100).quantize(Decimal('0.01'))


