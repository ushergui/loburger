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

    def _fmt(self, valor, casas=3):
        from django.utils.formats import number_format
        q = Decimal(valor).quantize(Decimal('1.' + '0' * casas)).normalize()
        return number_format(q, use_l10n=True, force_grouping=True)

    @property
    def estoque_display(self):
        """Estoque numa unidade amigável e no formato brasileiro
        (compra em kg/l → mostra em kg/l; ex.: 5.450 g vira '5,450 kg')."""
        fator = self.obter_fator_conversao
        if fator > 1:
            return f"{self._fmt((self.estoque_atual or 0) / fator)} {self.unidade_compra}"
        return f"{self._fmt(self.estoque_atual or 0)} {self.unidade_medida}"

    @property
    def estoque_minimo_display(self):
        fator = self.obter_fator_conversao
        if fator > 1:
            return f"{self._fmt((self.estoque_minimo or 0) / fator)} {self.unidade_compra}"
        return f"{self._fmt(self.estoque_minimo or 0)} {self.unidade_medida}"

    @property
    def custo_por_unidade_compra(self):
        """Custo por kg / litro / unidade (como você compra)."""
        return (self.custo_unitario * self.obter_fator_conversao).quantize(Decimal('0.01'))


class Produto(models.Model):
    CATEGORIAS = (
        ('BURGER', 'Hambúrgueres (Campeões)'),
        ('BEBIDA', 'Bebidas'),
        ('ACOMPANHAMENTO', 'Acompanhamentos e Fritas'),
        ('COMBO', 'Combos Hextech'),
        ('ENTRADA', 'Entradas e Porções'),
        ('CROISSANT', 'Croissants'),
        ('SOBREMESA', 'Sobremesas e Mimos'),
        ('ADICIONAL', 'Adicionais (extras do lanche)'),
    )

    nome = models.CharField(max_length=100, verbose_name="Nome do Produto")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='BURGER', verbose_name="Categoria")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição do Lanche")
    foto = models.ImageField(upload_to='produtos/', blank=True, null=True, verbose_name="Foto do Lanche")
    status = models.BooleanField(default=True, verbose_name="Ativo / Em Linha")
    custo_aquisicao = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        verbose_name="Custo de aquisição (revenda)",
        help_text="Só para itens de revenda comprados prontos (refrigerante, água, chocolate). "
                  "Deixe 0 para produtos feitos por ficha técnica.")

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def _calcular_custo(self, visitados):
        if self.pk in visitados:
            return Decimal('0.00')
        visitados = visitados | {self.pk}
        custo = Decimal(self.custo_aquisicao or 0)
        for item in self.ficha_tecnica.all():
            if item.ingrediente_id:
                custo += item.quantidade * item.ingrediente.custo_unitario
            elif item.produto_componente_id:
                custo += item.quantidade * item.produto_componente._calcular_custo(visitados)
        return custo.quantize(Decimal('0.01'))

    @property
    def custo_total(self):
        """Custo de produção: revenda (custo_aquisicao) + soma da ficha técnica.
        A ficha pode ter ingredientes E outros produtos (combos), recursivamente."""
        return self._calcular_custo(set())

    def insumos_consolidados(self, multiplicador=Decimal('1'), _visitados=None):
        """{ingrediente_id: (ingrediente, quantidade_total)} — a ficha achatada,
        entrando recursivamente nos produtos componentes (combos)."""
        _visitados = _visitados or set()
        resultado = {}
        if self.pk in _visitados:
            return resultado
        _visitados = _visitados | {self.pk}
        for item in self.ficha_tecnica.select_related('ingrediente', 'produto_componente').all():
            qtd = item.quantidade * multiplicador
            if item.ingrediente_id:
                ing = item.ingrediente
                atual = resultado.get(ing.id, (ing, Decimal('0')))
                resultado[ing.id] = (ing, atual[1] + qtd)
            elif item.produto_componente_id:
                sub = item.produto_componente.insumos_consolidados(qtd, _visitados)
                for iid, (ing, q) in sub.items():
                    atual = resultado.get(iid, (ing, Decimal('0')))
                    resultado[iid] = (ing, atual[1] + q)
        return resultado


class FichaTecnicaItem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='ficha_tecnica', verbose_name="Produto")
    ingrediente = models.ForeignKey(Ingrediente, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Ingrediente / Insumo")
    produto_componente = models.ForeignKey(
        Produto, on_delete=models.CASCADE, null=True, blank=True,
        related_name='usado_em_combos', verbose_name="Produto componente (combo)")
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, verbose_name="Quantidade Utilizada")

    class Meta:
        verbose_name = "Item de Ficha Técnica"
        verbose_name_plural = "Itens de Ficha Técnica"
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(ingrediente__isnull=False, produto_componente__isnull=True)
                    | models.Q(ingrediente__isnull=True, produto_componente__isnull=False)
                ),
                name='ficha_item_ingrediente_xor_produto',
            ),
        ]

    def __str__(self):
        alvo = self.ingrediente or self.produto_componente
        return f"{self.quantidade} de {alvo} em {self.produto.nome}"

    @property
    def componente_nome(self):
        if self.ingrediente_id:
            return self.ingrediente.nome
        return f"{self.produto_componente.nome} (produto)"

    @property
    def unidade(self):
        return self.ingrediente.unidade_medida if self.ingrediente_id else 'un'

    @property
    def custo_item(self):
        if self.ingrediente_id:
            base = self.ingrediente.custo_unitario
        elif self.produto_componente_id:
            base = self.produto_componente.custo_total
        else:
            base = Decimal('0')
        return (self.quantidade * base).quantize(Decimal('0.01'))


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


