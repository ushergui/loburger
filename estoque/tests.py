from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from produtos.models import Ingrediente
from estoque.models import MovimentacaoEstoque
from relatorios.models import Despesa

Usuario = get_user_model()


class EstoqueAjustarTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='op', password='x', role='GESTAO')
        self.client.force_login(self.user)
        self.carne = Ingrediente.objects.create(
            nome='CARNE TESTE', unidade_medida='g', unidade_compra='kg',
            custo_unitario=Decimal('0'), estoque_atual=Decimal('0'),
            estoque_minimo=Decimal('0'))

    def test_abertura_sem_valor_nao_salva_e_mostra_erro(self):
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id,
            'quantidade': '2',
            'tipo': 'ABERTURA',
            'valor_unitario': '',
            'observacao': '',
        })
        self.assertEqual(resp.status_code, 200)  # re-renderiza, não redireciona
        self.assertContains(resp, 'Não foi possível salvar')
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_entrada_nao_e_mais_opcao_no_ajuste(self):
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id, 'quantidade': '2', 'tipo': 'ENTRADA',
            'valor_unitario': '45,50', 'observacao': '',
        })
        self.assertEqual(resp.status_code, 200)  # ENTRADA rejeitada aqui
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_abertura_tambem_exige_e_aceita_o_custo(self):
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id,
            'quantidade': '5,450',
            'tipo': 'ABERTURA',
            'valor_unitario': '44,00',
            'observacao': '',
        })
        self.assertRedirects(resp, reverse('estoque_resumo'))
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('5450'))
        # abertura NÃO gera despesa
        self.assertEqual(Despesa.objects.filter(origem='ESTOQUE').count(), 0)

    def test_saida_perda_baixa_sem_exigir_custo(self):
        self.carne.estoque_atual = Decimal('1000')
        self.carne.save()
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id,
            'quantidade': '0,2',
            'tipo': 'SAIDA_PERDA',
            'observacao': 'estragou',
        })
        self.assertRedirects(resp, reverse('estoque_resumo'))
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('800'))  # 1000 - 200 g


class EstoqueCompraTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username='c', password='x', role='GESTAO')
        self.client.force_login(self.user)
        self.carne = Ingrediente.objects.create(
            nome='CARNE', unidade_medida='g', unidade_compra='kg',
            custo_unitario=Decimal('0'), estoque_atual=Decimal('0'), estoque_minimo=Decimal('0'))
        self.pao = Ingrediente.objects.create(
            nome='PAO', unidade_medida='un', unidade_compra='un',
            custo_unitario=Decimal('0'), estoque_atual=Decimal('0'), estoque_minimo=Decimal('0'))

    def _add(self, ing, qtd, vu):
        return self.client.post(reverse('estoque_compra'), {
            'acao': 'add_item', 'ingrediente': ing.id, 'quantidade': qtd, 'valor_unitario': vu})

    def test_carrinho_avista_gera_uma_despesa_paga(self):
        self._add(self.carne, '2', '45,00')
        self._add(self.pao, '30', '1,50')
        resp = self.client.post(reverse('estoque_compra'), {
            'acao': 'finalizar', 'forma_pagamento': 'AVISTA', 'credor': 'Assai'})
        self.assertRedirects(resp, reverse('estoque_resumo'))
        self.carne.refresh_from_db(); self.pao.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('2000'))
        self.assertEqual(self.pao.estoque_atual, Decimal('30'))
        d = Despesa.objects.get(origem='ESTOQUE')
        self.assertEqual(d.status, 'PAGO')
        self.assertEqual(d.valor, Decimal('135.00'))  # 90 + 45
        self.assertEqual(d.forma_pagamento, 'AVISTA')
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo='ENTRADA').count(), 2)

    def test_carrinho_cartao_gera_despesa_prevista_com_vencimento(self):
        self._add(self.carne, '1', '50,00')
        resp = self.client.post(reverse('estoque_compra'), {
            'acao': 'finalizar', 'forma_pagamento': 'CARTAO',
            'credor': 'Cartão Nubank', 'data_vencimento': '2026-10-10'})
        self.assertRedirects(resp, reverse('estoque_resumo'))
        d = Despesa.objects.get(origem='ESTOQUE')
        self.assertEqual(d.status, 'PREVISTO')
        self.assertIsNone(d.data_pagamento)
        self.assertEqual(str(d.data_vencimento), '2026-10-10')
        self.assertEqual(d.credor, 'Cartão Nubank')

    def test_cartao_sem_data_nao_finaliza(self):
        self._add(self.carne, '1', '50,00')
        resp = self.client.post(reverse('estoque_compra'), {
            'acao': 'finalizar', 'forma_pagamento': 'BOLETO', 'credor': 'x'})
        self.assertRedirects(resp, reverse('estoque_compra'))
        self.assertEqual(Despesa.objects.filter(origem='ESTOQUE').count(), 0)

    def test_editar_compra_reabre_carrinho_e_estorna(self):
        self._add(self.carne, '2', '45,00')   # 2 kg a 45 -> 90
        self._add(self.pao, '10', '2,00')     # 10 un a 2 -> 20
        self.client.post(reverse('estoque_compra'), {
            'acao': 'finalizar', 'forma_pagamento': 'CARTAO',
            'credor': 'Cartão X', 'data_vencimento': '2026-10-10'})
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('2000'))
        d = Despesa.objects.get(origem='ESTOQUE')

        # abre a confirmação e confirma
        self.assertEqual(self.client.get(reverse('estoque_compra_editar', args=[d.id])).status_code, 200)
        resp = self.client.post(reverse('estoque_compra_editar', args=[d.id]))
        self.assertRedirects(resp, reverse('estoque_compra'))

        # despesa e movimentações sumiram, estoque estornado
        self.assertEqual(Despesa.objects.filter(origem='ESTOQUE').count(), 0)
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo='ENTRADA').count(), 0)
        self.carne.refresh_from_db(); self.pao.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('0'))
        self.assertEqual(self.pao.estoque_atual, Decimal('0'))

        # carrinho recarregado com os 2 itens, na unidade de compra
        cart = self.client.session['compra_cart']
        self.assertEqual(len(cart), 2)
        nomes = {c['nome'] for c in cart}
        self.assertEqual(nomes, {'CARNE', 'PAO'})
        carne_item = next(c for c in cart if c['nome'] == 'CARNE')
        self.assertEqual(Decimal(carne_item['quantidade']), Decimal('2'))
        self.assertEqual(Decimal(carne_item['valor_unitario']), Decimal('45'))

    def test_excluir_compra_estorna_estoque(self):
        self._add(self.carne, '1', '50,00')
        self.client.post(reverse('estoque_compra'), {
            'acao': 'finalizar', 'forma_pagamento': 'AVISTA'})
        d = Despesa.objects.get(origem='ESTOQUE')
        self.client.post(reverse('despesa_excluir', args=[d.id]))
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('0'))
        self.assertEqual(Despesa.objects.filter(origem='ESTOQUE').count(), 0)

    def test_pagar_lote(self):
        d1 = Despesa.objects.create(descricao='c1', categoria='FORNECEDORES', valor=Decimal('100'),
                                    status='PREVISTO', data_vencimento='2026-10-10', forma_pagamento='CARTAO')
        d2 = Despesa.objects.create(descricao='c2', categoria='FORNECEDORES', valor=Decimal('50'),
                                    status='PREVISTO', data_vencimento='2026-10-10', forma_pagamento='CARTAO')
        resp = self.client.post(reverse('despesa_pagar_lote'), {
            'ids': [d1.id, d2.id], 'data_pagamento': '2026-10-10'})
        self.assertRedirects(resp, reverse('despesa_listar'))
        d1.refresh_from_db(); d2.refresh_from_db()
        self.assertEqual(d1.status, 'PAGO')
        self.assertEqual(d2.status, 'PAGO')
        self.assertEqual(str(d1.data_pagamento), '2026-10-10')
