from decimal import Decimal

from django.test import TestCase

from produtos.models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal
from vendas.models import CanalVenda, ConfiguracaoFinanceira, Pedido, PedidoItem


class ComboComposicaoTests(TestCase):
    def setUp(self):
        ConfiguracaoFinanceira.get_solo()
        self.canal = CanalVenda.objects.create(nome='iFood', taxa_comissao=Decimal('0'), taxa_online=Decimal('0'))

        self.pao = Ingrediente.objects.create(nome='PAO', unidade_medida='un', unidade_compra='un',
                                              custo_unitario=Decimal('1.00'), estoque_atual=Decimal('100'))
        self.batata_ing = Ingrediente.objects.create(nome='BATATA', unidade_medida='g', unidade_compra='kg',
                                                     custo_unitario=Decimal('0.01'), estoque_atual=Decimal('5000'))

        self.lanche = Produto.objects.create(nome='X Burguer', categoria='BURGER')
        FichaTecnicaItem.objects.create(produto=self.lanche, ingrediente=self.pao, quantidade=Decimal('1'))

        self.batata = Produto.objects.create(nome='Batata', categoria='ACOMPANHAMENTO')
        FichaTecnicaItem.objects.create(produto=self.batata, ingrediente=self.batata_ing, quantidade=Decimal('150'))

        self.refri = Produto.objects.create(nome='Coca Lata', categoria='BEBIDA', custo_aquisicao=Decimal('2.50'))

        self.combo = Produto.objects.create(nome='Combo Teste', categoria='COMBO')
        FichaTecnicaItem.objects.create(produto=self.combo, produto_componente=self.lanche, quantidade=Decimal('1'))
        FichaTecnicaItem.objects.create(produto=self.combo, produto_componente=self.batata, quantidade=Decimal('1'))
        FichaTecnicaItem.objects.create(produto=self.combo, produto_componente=self.refri, quantidade=Decimal('1'))

    def test_custo_do_combo_soma_componentes(self):
        # lanche 1,00 + batata (150 * 0,01 = 1,50) + refri revenda 2,50 = 5,00
        self.assertEqual(self.combo.custo_total, Decimal('5.00'))

    def test_revenda_usa_custo_aquisicao(self):
        self.assertEqual(self.refri.custo_total, Decimal('2.50'))

    def test_vender_combo_baixa_estoque_dos_componentes(self):
        p = Pedido.objects.create(canal=self.canal, modo_pagamento='DINHEIRO', status='CONCLUIDO')
        PedidoItem.objects.create(pedido=p, produto=self.combo, quantidade=2, preco_unitario=Decimal('30'))
        p.recalcular_valores_financeiros(save=True)
        p.processar_baixa_estoque()

        self.pao.refresh_from_db()
        self.batata_ing.refresh_from_db()
        self.assertEqual(self.pao.estoque_atual, Decimal('98'))       # 100 - 2 combos * 1 pão
        self.assertEqual(self.batata_ing.estoque_atual, Decimal('4700'))  # 5000 - 2 * 150

    def test_protecao_contra_referencia_circular(self):
        # combo aponta pra si mesmo — não deve estourar recursão
        FichaTecnicaItem.objects.create(produto=self.combo, produto_componente=self.combo, quantidade=Decimal('1'))
        _ = self.combo.custo_total  # não levanta RecursionError
        self.assertTrue(True)
