from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.utils import timezone

from produtos.models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal
from vendas.models import (
    CanalVenda, ConfiguracaoFinanceira, Entregador, EntregaDiaria,
    Pedido, PedidoItem,
)
from vendas.services import sincronizar_despesas_fechamento
from relatorios.models import Despesa
from relatorios import services as rel_services


class BaseFinanceiro(TestCase):
    def setUp(self):
        cfg = ConfiguracaoFinanceira.get_solo()
        cfg.taxa_maquininha = Decimal('0.0350')
        cfg.taxa_online_plataforma = Decimal('0.0320')
        cfg.taxa_entrega = Decimal('9.00')
        cfg.caixa_inicial = Decimal('0.00')
        cfg.save()

        self.ifood = CanalVenda.objects.create(nome='iFood', taxa_comissao=Decimal('0.1200'), taxa_fixa=Decimal('0'))

        self.pao = Ingrediente.objects.create(nome='Pao', unidade_medida='un', unidade_compra='un',
                                              custo_unitario=Decimal('1.0000'), estoque_atual=Decimal('100'))
        self.burger = Produto.objects.create(nome='X', categoria='BURGER')
        FichaTecnicaItem.objects.create(produto=self.burger, ingrediente=self.pao, quantidade=Decimal('2'))
        PrecoCanal.objects.create(produto=self.burger, canal=self.ifood, preco=Decimal('50.00'))

    def _pedido(self, modo, qtd=1, desconto=Decimal('0')):
        p = Pedido.objects.create(canal=self.ifood, modo_pagamento=modo, status='CONCLUIDO', desconto=desconto)
        PedidoItem.objects.create(pedido=p, produto=self.burger, quantidade=qtd, preco_unitario=Decimal('50.00'))
        p.recalcular_valores_financeiros(save=True)
        p.refresh_from_db()
        return p


class RecalculoFinanceiroTests(BaseFinanceiro):
    def test_online_soma_comissao_e_acrescimo(self):
        p = self._pedido('ONLINE', qtd=2)  # bruto 100
        self.assertEqual(p.valor_bruto, Decimal('100.00'))
        self.assertEqual(p.taxas_canal, Decimal('12.00'))       # 12%
        self.assertEqual(p.taxas_pagamento, Decimal('3.20'))    # +3,2%
        self.assertEqual(p.lucro_liquido, Decimal('84.80'))     # 100 - 12 - 3.20

    def test_maquininha_usa_taxa_da_config(self):
        p = self._pedido('MAQUININHA', qtd=2)
        self.assertEqual(p.taxas_pagamento, Decimal('3.50'))    # 3,5% de 100
        self.assertEqual(p.lucro_liquido, Decimal('84.50'))

    def test_dinheiro_na_entrega_sem_taxa_de_pagamento(self):
        p = self._pedido('DINHEIRO', qtd=2)
        self.assertEqual(p.taxas_pagamento, Decimal('0.00'))
        self.assertEqual(p.lucro_liquido, Decimal('88.00'))

    def test_cmv_nao_abate_o_liquido_mas_entra_na_margem(self):
        p = self._pedido('DINHEIRO', qtd=1)  # bruto 50, cmv = 2 paes * 1.00 = 2.00
        self.assertEqual(p.custo_ingredientes, Decimal('2.00'))
        self.assertEqual(p.lucro_liquido, Decimal('44.00'))                 # 50 - 6 (12%)
        self.assertEqual(p.margem_contribuicao, Decimal('42.00'))           # ... - 2 de insumo

    def test_desconto_reduz_o_liquido(self):
        p = self._pedido('DINHEIRO', qtd=2, desconto=Decimal('10'))
        self.assertEqual(p.lucro_liquido, Decimal('78.00'))                 # 100 - 12 - 10


class DespesasDoFechamentoTests(BaseFinanceiro):
    def test_gera_taxa_plataforma_maquininha_e_motoboy(self):
        hoje = timezone.localdate()
        self._pedido('ONLINE', qtd=2)      # taxa canal 12 + online 3,20
        self._pedido('MAQUININHA', qtd=2)  # taxa canal 12 + maquininha 3,50

        socio = Entregador.objects.create(nome='Igor', eh_socio=True)
        ze = Entregador.objects.create(nome='Ze', eh_socio=False)
        EntregaDiaria.objects.create(data=hoje, entregador=socio, quantidade=2)
        EntregaDiaria.objects.create(data=hoje, entregador=ze, quantidade=3)

        n = sincronizar_despesas_fechamento(hoje)
        self.assertEqual(n, 3)

        plataforma = Despesa.objects.get(categoria='TAXA_PLATAFORMA', data_referencia=hoje)
        self.assertEqual(plataforma.valor, Decimal('27.20'))   # 12 + 3,20 + 12
        maquininha = Despesa.objects.get(categoria='TAXA_MAQUININHA', data_referencia=hoje)
        self.assertEqual(maquininha.valor, Decimal('3.50'))
        motoboy = Despesa.objects.get(categoria='ENTREGA', data_referencia=hoje)
        self.assertEqual(motoboy.valor, Decimal('27.00'))      # só o Ze: 3 * 9
        self.assertIn('Ze', motoboy.descricao)

    def test_idempotente(self):
        hoje = timezone.localdate()
        self._pedido('ONLINE', qtd=1)
        sincronizar_despesas_fechamento(hoje)
        sincronizar_despesas_fechamento(hoje)
        self.assertEqual(Despesa.objects.filter(origem='FECHAMENTO', data_referencia=hoje).count(), 1)


class ResumoFinanceiroTests(BaseFinanceiro):
    def test_taxas_nao_sao_contadas_duas_vezes(self):
        hoje = timezone.localdate()
        p = self._pedido('ONLINE', qtd=2)  # liquido 84,80
        sincronizar_despesas_fechamento(hoje)  # cria Despesa TAXA_PLATAFORMA 15,20 (paga)

        r = rel_services.resumo_financeiro(hoje, hoje)
        # entradas = liquido; saidas de caixa excluem as taxas embutidas
        self.assertEqual(r['entradas_caixa'], Decimal('84.80'))
        self.assertEqual(r['saidas_caixa'], Decimal('0.00'))
        self.assertEqual(r['resultado_caixa'], Decimal('84.80'))

    def test_lucro_economico_soma_compras_e_desconta_cmv(self):
        hoje = timezone.localdate()
        self._pedido('DINHEIRO', qtd=1)  # cmv 2,00, liquido 44,00
        Despesa.objects.create(descricao='Compra pao', categoria='FORNECEDORES', valor=Decimal('30.00'),
                               tipo='VARIAVEL', status='PAGO', data_vencimento=hoje, data_pagamento=hoje,
                               origem='ESTOQUE')
        r = rel_services.resumo_financeiro(hoje, hoje)
        # caixa = 44 - 30 = 14 ; economico = 14 + 30 - 2 = 42
        self.assertEqual(r['resultado_caixa'], Decimal('14.00'))
        self.assertEqual(r['lucro_economico'], Decimal('42.00'))

    def test_entregas_entram_no_caixa_e_socio_fica_com_o_valor(self):
        hoje = timezone.localdate()
        ze = Entregador.objects.create(nome='Ze', eh_socio=False)
        igor = Entregador.objects.create(nome='Igor', eh_socio=True)
        EntregaDiaria.objects.create(data=hoje, entregador=ze, quantidade=2)
        EntregaDiaria.objects.create(data=hoje, entregador=igor, quantidade=1)
        sincronizar_despesas_fechamento(hoje)

        r = rel_services.resumo_financeiro(hoje, hoje)
        # receita: 3 entregas * 9 = 27 ; custo motoboy (só Ze): 18 ; sobra 9 (do Igor)
        self.assertEqual(r['receita_entregas'], Decimal('27.00'))
        self.assertEqual(r['resultado_caixa'], Decimal('9.00'))
