from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from estoque.models import MovimentacaoEstoque
from produtos.models import Produto, PrecoCanal
from relatorios.models import Despesa
from vendas.models import Entregador, EntregaDiaria, Pedido, PedidoItem
from vendas.tests import BaseFinanceiro


class FechamentoAutosaveTests(BaseFinanceiro):
    """Salvamento célula a célula do Fechamento Diário (a tela grava sozinha cada campo)."""

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user('caixa', password='x', role='GESTAO')
        self.client.force_login(self.user)
        self.hoje = timezone.localdate()
        self.url = '/vendas/fechamento-diario/celula/'

    def _salvar(self, campo, valor, data=None):
        data = data or self.hoje
        data = data if isinstance(data, str) else data.isoformat()
        return self.client.post(self.url, {'data': data, 'campo': campo, 'valor': valor})

    def _celula(self, modo='ONLINE', produto=None, canal=None):
        return f"qtd_{(produto or self.burger).id}_{(canal or self.ifood).id}_{modo}"

    def _pao(self):
        self.pao.refresh_from_db()
        return self.pao.estoque_atual

    def _tela(self):
        return self.client.get(f'/vendas/fechamento-diario/?data={self.hoje.isoformat()}').content.decode()

    def _salvar_tudo(self, extra=None):
        dados = {'data': self.hoje.isoformat(), 'desconto_dia': '0'}
        dados.update(extra or {})
        return self.client.post(f'/vendas/fechamento-diario/?data={self.hoje.isoformat()}', dados)

    # ---------------------------------------------------------------- quantidades
    def test_digitar_cria_o_pedido_baixa_estoque_e_calcula_taxas(self):
        r = self._salvar(self._celula('ONLINE'), '3')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['ok'])
        ped = Pedido.objects.get()
        self.assertEqual((ped.status, ped.modo_pagamento, ped.estoque_baixado), ('CONCLUIDO', 'ONLINE', True))
        self.assertEqual(ped.valor_bruto, Decimal('150.00'))
        self.assertEqual(ped.taxas_canal, Decimal('22.80'))          # 15,2% de 150
        self.assertEqual(self._pao(), Decimal('94.00'))              # 3 x 2 pães
        self.assertEqual(r.json()['total_bruto'], '150.00')
        self.assertTrue(Despesa.objects.filter(origem='FECHAMENTO', valor=Decimal('22.80')).exists())

    def test_mudar_a_quantidade_ajusta_so_a_diferenca(self):
        self._salvar(self._celula(), '3')
        self._salvar(self._celula(), '5')
        self.assertEqual(self._pao(), Decimal('90.00'))              # 5 x 2 = 10 pães
        self._salvar(self._celula(), '2')
        self.assertEqual(self._pao(), Decimal('96.00'))              # volta a 4
        self.assertEqual(PedidoItem.objects.get().quantidade, 2)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_zerar_remove_o_item_o_pedido_e_devolve_o_estoque(self):
        self._salvar(self._celula(), '4')
        self._salvar(self._celula(), '')                             # campo vazio = 0
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(PedidoItem.objects.count(), 0)
        self.assertEqual(self._pao(), Decimal('100.00'))
        self.assertFalse(Despesa.objects.filter(origem='FECHAMENTO').exists())

    def test_salvar_o_mesmo_valor_duas_vezes_nao_mexe_no_estoque(self):
        self._salvar(self._celula(), '3')
        self._salvar(self._celula(), '3')
        self.assertEqual(self._pao(), Decimal('94.00'))
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo='SAIDA_VENDA').count(), 1)

    def test_celulas_de_modos_diferentes_viram_pedidos_diferentes(self):
        self._salvar(self._celula('ONLINE'), '1')
        self._salvar(self._celula('MAQUININHA'), '2')
        self.assertEqual(Pedido.objects.count(), 2)
        self.assertEqual(self._pao(), Decimal('94.00'))
        self.assertTrue(Despesa.objects.filter(categoria='TAXA_MAQUININHA').exists())

    def test_dois_produtos_no_mesmo_canal_e_modo_dividem_o_pedido(self):
        suco = Produto.objects.create(nome='Suco', categoria='BEBIDA')
        PrecoCanal.objects.create(produto=suco, canal=self.ifood, preco=Decimal('8.00'))
        self._salvar(self._celula('ONLINE'), '1')
        self._salvar(self._celula('ONLINE', produto=suco), '2')
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Pedido.objects.get().valor_bruto, Decimal('66.00'))   # 50 + 2 x 8

    def test_dia_diferente_do_de_hoje(self):
        ontem = self.hoje - timedelta(days=1)
        self._salvar(self._celula(), '2', data=ontem)
        criado = Pedido.objects.get().data_criacao.astimezone(timezone.get_current_timezone()).date()
        self.assertEqual(criado, ontem)

    def test_sem_preco_no_canal_avisa_e_lanca_zero(self):
        suco = Produto.objects.create(nome='Suco', categoria='BEBIDA')
        r = self._salvar(self._celula('ONLINE', produto=suco), '1')
        self.assertTrue(r.json()['sem_preco'])
        self.assertEqual(Pedido.objects.get().valor_bruto, Decimal('0.00'))

    def test_entrada_invalida_e_recusada(self):
        for valor in ('abc', '-2', '1,5', '99999'):
            r = self._salvar(self._celula(), valor)
            self.assertEqual(r.status_code, 400, valor)
            self.assertFalse(r.json()['ok'])
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(self._salvar('qtd_1_1_XYZ', '1').status_code, 400)
        self.assertEqual(self._salvar('campo_qualquer', '1').status_code, 400)
        self.assertEqual(self._salvar(self._celula(), '1', data='data-ruim').status_code, 400)

    def test_exige_login_e_post(self):
        self.client.logout()
        self.assertEqual(self._salvar(self._celula(), '1').status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    # ---------------------------------------------------------------- desconto e entregas
    def test_desconto_fica_no_primeiro_pedido_e_vale_uma_vez(self):
        self._salvar(self._celula('ONLINE'), '2')
        self._salvar(self._celula('MAQUININHA'), '2')
        self._salvar('desconto_dia', '10,00')
        primeiro, segundo = Pedido.objects.order_by('id')
        self.assertEqual((primeiro.desconto, segundo.desconto), (Decimal('10.00'), Decimal('0.00')))
        # remover o primeiro pedido: o desconto passa para o que sobrou
        self._salvar(self._celula('ONLINE'), '0')
        self.assertEqual(Pedido.objects.get().desconto, Decimal('10.00'))

    def test_desconto_digitado_antes_de_qualquer_venda_nao_se_perde(self):
        self._salvar('desconto_dia', '7,50')
        self.assertEqual(Pedido.objects.count(), 0)
        self._salvar(self._celula(), '1')
        self.assertEqual(Pedido.objects.get().desconto, Decimal('7.50'))
        self.assertIn('7,50', self._tela())

    def test_desconto_negativo_e_recusado(self):
        self.assertEqual(self._salvar('desconto_dia', '-5').status_code, 400)

    def test_entregas_salvam_e_geram_despesa_de_motoboy(self):
        serginho = Entregador.objects.create(nome='Serginho', ativo=True)
        r = self._salvar(f'entrega_{serginho.id}', '4')
        self.assertTrue(r.json()['ok'])
        self.assertEqual(EntregaDiaria.objects.get(entregador=serginho).quantidade, 4)
        self.assertTrue(Despesa.objects.filter(categoria='ENTREGA', valor=Decimal('36.00')).exists())
        self._salvar(f'entrega_{serginho.id}', '0')
        self.assertFalse(Despesa.objects.filter(categoria='ENTREGA').exists())

    # ---------------------------------------------------------------- tela e "salvar tudo"
    def test_tela_mostra_o_que_ja_foi_salvo(self):
        self._salvar(self._celula('ONLINE'), '6')
        html = self._tela()
        self.assertIn(f'name="{self._celula("ONLINE")}" data-autosave data-ultimo="6"', html)
        self.assertIn('Tudo salvo', html)
        self.assertNotIn('hx-target="#tabela-fechamento"', html)   # o filtro não recarrega mais a tabela pelo servidor

    def test_salvar_tudo_depois_do_autosave_nao_muda_nada(self):
        """O botão 'Conferir e salvar tudo' reenvia a tela inteira: o resultado tem que ser o mesmo."""
        self._salvar(self._celula('ONLINE'), '3')
        self._salvar(self._celula('MAQUININHA'), '1')
        self._salvar('desconto_dia', '5,00')
        antes = (self._pao(), sorted(Pedido.objects.values_list('modo_pagamento', 'valor_bruto')))
        r = self._salvar_tudo({'desconto_dia': '5,00', self._celula('ONLINE'): '3', self._celula('MAQUININHA'): '1'})
        self.assertEqual(r.status_code, 302)
        depois = (self._pao(), sorted(Pedido.objects.values_list('modo_pagamento', 'valor_bruto')))
        self.assertEqual(antes, depois)
        self.assertEqual(sum(p.desconto for p in Pedido.objects.all()), Decimal('5.00'))

    def test_salvar_tudo_cancela_corretamente_pedidos_criados_pelo_autosave(self):
        self._salvar(self._celula('ONLINE'), '5')
        self._salvar_tudo()                                            # tela sem nenhuma quantidade
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(self._pao(), Decimal('100.00'))

    def test_despesas_automaticas_so_mudam_o_que_mudou(self):
        self._salvar(self._celula('ONLINE'), '3')
        id_antes = Despesa.objects.get(categoria='TAXA_PLATAFORMA').id
        self._salvar('desconto_dia', '1,00')                           # não muda as taxas
        self.assertEqual(Despesa.objects.get(categoria='TAXA_PLATAFORMA').id, id_antes)
        self._salvar(self._celula('ONLINE'), '4')                      # muda o valor da taxa
        d = Despesa.objects.get(categoria='TAXA_PLATAFORMA')
        self.assertEqual((d.id, d.valor), (id_antes, Decimal('30.40')))
