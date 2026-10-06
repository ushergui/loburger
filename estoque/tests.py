from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


class EstoqueContagemTests(TestCase):
    """Contagem: digita o que tem de verdade; o sistema acerta a diferença sem despesa."""

    def setUp(self):
        self.user = Usuario.objects.create_user(username='ges', password='x', role='GESTAO')
        self.client.force_login(self.user)
        # carne: g (compra em kg) -> 5 kg = 5000 g, custo R$ 40/kg = 0,04/g
        self.carne = Ingrediente.objects.create(
            nome='CARNE', unidade_medida='g', unidade_compra='kg',
            custo_unitario=Decimal('0.0400'), estoque_atual=Decimal('5000'))
        self.saco = Ingrediente.objects.create(
            nome='SACO', unidade_medida='un', unidade_compra='un',
            custo_unitario=Decimal('45.0000'), estoque_atual=Decimal('1000'))

    def _post(self, **extra):
        dados = {
            f'qtd_{self.carne.id}': '5', f'custo_{self.carne.id}': '40',
            f'qtd_{self.saco.id}': '1000', f'custo_{self.saco.id}': '45',
        }
        dados.update(extra)
        return self.client.post(reverse('estoque_contagem'), dados)

    def test_tela_abre_com_os_valores_do_sistema(self):
        resp = self.client.get(reverse('estoque_contagem'))
        self.assertContains(resp, 'CARNE')
        self.assertContains(resp, 'Isto NÃO é compra')

    def test_sem_mudanca_nao_grava_nada(self):
        resp = self._post()
        self.assertRedirects(resp, reverse('estoque_contagem'))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_quantidade_maior_entra_como_abertura_sem_despesa(self):
        self._post(**{f'qtd_{self.carne.id}': '8,5'})
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('8500.00'))
        mov = MovimentacaoEstoque.objects.get()
        self.assertEqual(mov.tipo, 'ABERTURA')
        self.assertEqual(mov.quantidade, Decimal('3500'))
        self.assertEqual(self.carne.custo_unitario, Decimal('0.0400'))  # custo não muda
        self.assertEqual(Despesa.objects.count(), 0)

    def test_quantidade_menor_baixa_como_ajuste_sem_despesa(self):
        self._post(**{f'qtd_{self.carne.id}': '1'})
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('1000.00'))
        mov = MovimentacaoEstoque.objects.get()
        self.assertEqual(mov.tipo, 'AJUSTE')
        self.assertEqual(mov.quantidade, Decimal('4000'))
        self.assertEqual(Despesa.objects.count(), 0)

    def test_ponto_de_milhar_e_entendido_como_mil(self):
        self._post(**{f'qtd_{self.saco.id}': '1.500'})
        self.saco.refresh_from_db()
        self.assertEqual(self.saco.estoque_atual, Decimal('1500.00'))

    def test_valores_preenchidos_pela_tela_voltam_iguais(self):
        """Salvar sem mexer em nada (campos como a tela os preenche) não pode alterar o estoque."""
        resp = self.client.get(reverse('estoque_contagem'))
        dados = {}
        # reconstrói o POST a partir do contexto da view (mesmos textos que a tela mostra)
        for l in resp.context['linhas']:
            dados[f"qtd_{l['ing'].id}"] = l['qtd_txt']
            dados[f"custo_{l['ing'].id}"] = l['custo_txt']
        self.assertEqual(dados[f'qtd_{self.saco.id}'], '1000')
        self.client.post(reverse('estoque_contagem'), dados)
        self.saco.refresh_from_db(); self.carne.refresh_from_db()
        self.assertEqual(self.saco.estoque_atual, Decimal('1000.00'))
        self.assertEqual(self.carne.estoque_atual, Decimal('5000.00'))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_corrige_custo_do_saquinho(self):
        self._post(**{f'custo_{self.saco.id}': '0,045'})
        self.saco.refresh_from_db()
        self.assertEqual(self.saco.custo_unitario, Decimal('0.0450'))
        self.assertEqual(self.saco.estoque_atual, Decimal('1000'))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_custo_em_kg_vira_custo_por_grama(self):
        self._post(**{f'custo_{self.carne.id}': '50'})
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.custo_unitario, Decimal('0.0500'))

    def test_linha_invalida_nao_grava_nada(self):
        resp = self._post(**{f'qtd_{self.carne.id}': '9', f'qtd_{self.saco.id}': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Nada foi salvo')
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('5000'))  # a linha válida também não gravou
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_negativo_e_recusado(self):
        resp = self._post(**{f'qtd_{self.carne.id}': '-3'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)

    def test_operador_nao_acessa(self):
        op = Usuario.objects.create_user(username='cx', password='x', role='OPERADOR')
        self.client.force_login(op)
        resp = self.client.get(reverse('estoque_contagem'))
        self.assertNotEqual(resp.status_code, 200)


class PagarLoteTravaTests(TestCase):
    """'Pagar selecionadas' não aceita conta que vence daqui a muito tempo."""

    def setUp(self):
        self.user = Usuario.objects.create_user(username='ges2', password='x', role='GESTAO')
        self.client.force_login(self.user)
        self.hoje = timezone.localdate()

    def _conta(self, dias):
        return Despesa.objects.create(
            descricao=f'Luz +{dias}', categoria='ENERGIA', tipo='FIXA', valor=Decimal('450'),
            status='PREVISTO', data_vencimento=self.hoje + timedelta(days=dias))

    def test_so_paga_as_que_vencem_em_ate_15_dias(self):
        perto, borda, longe = self._conta(3), self._conta(15), self._conta(40)
        resp = self.client.post(reverse('despesa_pagar_lote'),
                                {'ids': [perto.id, borda.id, longe.id]}, follow=True)
        perto.refresh_from_db(); borda.refresh_from_db(); longe.refresh_from_db()
        self.assertEqual(perto.status, 'PAGO')
        self.assertEqual(borda.status, 'PAGO')
        self.assertEqual(longe.status, 'PREVISTO')
        self.assertIsNone(longe.data_pagamento)
        self.assertContains(resp, 'NÃO foram pagas')

    def test_lista_desabilita_checkbox_das_contas_longe(self):
        self._conta(3)
        longe = self._conta(60)
        resp = self.client.get(reverse('despesa_listar'))
        self.assertNotContains(resp, f'name="ids" value="{longe.id}"')
        self.assertContains(resp, 'Para pagar adiantado')


class CorrecaoBaconBaldeTests(TestCase):
    """Migration de dados 0007: só age se achar exatamente os registros errados."""

    def _corrigir(self):
        import importlib
        from django.apps import apps
        mod = importlib.import_module('estoque.migrations.0007_corrige_bacon_e_detergente')
        mod.corrigir(apps, None)

    def setUp(self):
        self.bacon = Ingrediente.objects.create(
            nome='BACON', unidade_medida='g', unidade_compra='kg',
            custo_unitario=Decimal('0.0346'), estoque_atual=Decimal('32870'))
        self.balde = Ingrediente.objects.create(
            nome='BALDE DE MANTEIGA', unidade_medida='ml', unidade_compra='kg',
            custo_unitario=Decimal('142'), estoque_atual=Decimal('3'))

    def _movs_bacon(self, com_saida_errada=True):
        MovimentacaoEstoque.objects.create(ingrediente=self.bacon, tipo='ABERTURA',
                                           quantidade=Decimal('98000'), observacao='')
        if com_saida_errada:
            MovimentacaoEstoque.objects.create(ingrediente=self.bacon, tipo='SAIDA_AUTOCONSUMO',
                                               quantidade=Decimal('196000'), observacao='cadastro errado')
        MovimentacaoEstoque.objects.create(ingrediente=self.bacon, tipo='ABERTURA',
                                           quantidade=Decimal('36000'), observacao='Carga inicial.')

    def test_apaga_o_par_errado_e_nao_mexe_no_estoque(self):
        self._movs_bacon()
        self._corrigir()
        tipos = list(MovimentacaoEstoque.objects.values_list('tipo', 'quantidade'))
        self.assertEqual(tipos, [('ABERTURA', Decimal('36000.000'))])  # a carga legítima fica
        self.bacon.refresh_from_db()
        self.assertEqual(self.bacon.estoque_atual, Decimal('32870.00'))

    def test_sem_a_saida_errada_nao_apaga_nada(self):
        self._movs_bacon(com_saida_errada=False)
        self._corrigir()
        self.assertEqual(MovimentacaoEstoque.objects.count(), 2)

    def test_balde_nao_e_alterado_peso_so_a_gestao_sabe(self):
        self._corrigir()
        self.balde.refresh_from_db()
        self.assertEqual((self.balde.unidade_medida, self.balde.unidade_compra), ('ml', 'kg'))

    def test_detergente_compra_vira_unidade_e_mantem_estoque_e_custo(self):
        det = Ingrediente.objects.create(
            nome='DETERGENTE', unidade_medida='un', unidade_compra='ml',
            custo_unitario=Decimal('2.96'), estoque_atual=Decimal('20'))
        self._corrigir()
        det.refresh_from_db()
        self.assertEqual((det.unidade_medida, det.unidade_compra), ('un', 'un'))
        self.assertEqual(det.estoque_atual, Decimal('20.00'))
        self.assertEqual(det.custo_unitario, Decimal('2.9600'))

    def test_rodar_duas_vezes_e_seguro(self):
        self._movs_bacon()
        self._corrigir()
        self._corrigir()
        self.assertEqual(MovimentacaoEstoque.objects.count(), 1)


class UnidadesCombinamTests(TestCase):
    """A unidade de compra tem que combinar com a de consumo (g-kg, ml-l, un-un)."""

    def setUp(self):
        self.user = Usuario.objects.create_user(username='ges3', password='x', role='GESTAO')
        self.client.force_login(self.user)

    def _dados(self, **extra):
        d = {'nome': 'MANTEIGA', 'unidade_medida': 'g', 'unidade_compra': 'kg',
             'fornecedor': '', 'estoque_minimo': '0', 'categoria': 'OUTROS'}
        d.update(extra)
        return d

    def test_pares_validos(self):
        for compra, medida in [('kg', 'g'), ('g', 'g'), ('kg', 'kg'), ('l', 'ml'), ('ml', 'ml'), ('l', 'l'), ('un', 'un')]:
            ing = Ingrediente(nome='X', unidade_compra=compra, unidade_medida=medida)
            self.assertTrue(ing.unidades_coerentes, (compra, medida))
            ing.full_clean(exclude=['custo_unitario', 'estoque_atual', 'estoque_minimo'])

    def test_pares_invalidos(self):
        for compra, medida in [('kg', 'ml'), ('l', 'g'), ('un', 'g'), ('g', 'un'), ('ml', 'l'), ('g', 'kg'), ('ml', 'un')]:
            self.assertFalse(Ingrediente(nome='X', unidade_compra=compra, unidade_medida=medida).unidades_coerentes,
                             (compra, medida))

    def test_cadastro_recusa_combinacao_errada(self):
        resp = self.client.post(reverse('ingrediente_criar'), self._dados(unidade_medida='ml', unidade_compra='kg'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'não combinam')
        self.assertFalse(Ingrediente.objects.filter(nome='MANTEIGA').exists())

    def test_cadastro_aceita_combinacao_certa(self):
        resp = self.client.post(reverse('ingrediente_criar'), self._dados())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Ingrediente.objects.filter(nome='MANTEIGA').exists())

    def test_nao_troca_unidade_de_consumo_de_insumo_que_esta_em_ficha(self):
        from produtos.models import Produto, FichaTecnicaItem
        ing = Ingrediente.objects.create(nome='CARNE', unidade_medida='g', unidade_compra='kg')
        prod = Produto.objects.create(nome='LANCHE', categoria='BURGER')
        FichaTecnicaItem.objects.create(produto=prod, ingrediente=ing, quantidade=Decimal('150'))
        resp = self.client.post(reverse('ingrediente_editar', args=[ing.pk]),
                                self._dados(nome='CARNE', unidade_medida='kg', unidade_compra='kg'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ficha(s) técnica(s)')
        ing.refresh_from_db()
        self.assertEqual(ing.unidade_medida, 'g')

    def test_troca_permitida_se_nao_esta_em_ficha(self):
        ing = Ingrediente.objects.create(nome='BALDE', unidade_medida='ml', unidade_compra='kg')  # cadastro torto antigo
        resp = self.client.post(reverse('ingrediente_editar', args=[ing.pk]),
                                self._dados(nome='BALDE', unidade_medida='g', unidade_compra='kg'))
        self.assertEqual(resp.status_code, 302)
        ing.refresh_from_db()
        self.assertEqual((ing.unidade_medida, ing.unidade_compra), ('g', 'kg'))

    def test_lista_avisa_insumo_com_unidades_erradas(self):
        Ingrediente.objects.create(nome='BALDE', unidade_medida='ml', unidade_compra='kg')
        resp = self.client.get(reverse('ingrediente_listar'))
        self.assertContains(resp, 'Unidades erradas')

    def test_contagem_trava_linha_com_unidades_erradas(self):
        torto = Ingrediente.objects.create(
            nome='BALDE', unidade_medida='ml', unidade_compra='kg',
            custo_unitario=Decimal('142'), estoque_atual=Decimal('3'))
        resp = self.client.get(reverse('estoque_contagem'))
        self.assertContains(resp, 'corrija o cadastro antes de contar')
        # mesmo que alguém force o POST, a linha é ignorada
        self.client.post(reverse('estoque_contagem'), {f'qtd_{torto.id}': '50', f'custo_{torto.id}': '1'})
        torto.refresh_from_db()
        self.assertEqual(torto.estoque_atual, Decimal('3.00'))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 0)
