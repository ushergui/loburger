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

    def test_entrada_aceita_valor_com_virgula(self):
        """O custo digitado no formato brasileiro (45,50) tem que ser aceito."""
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id,
            'quantidade': '2',
            'tipo': 'ENTRADA',
            'valor_unitario': '45,50',
            'observacao': '',
        })
        self.assertRedirects(resp, reverse('estoque_resumo'))
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, Decimal('2000'))  # 2 kg -> 2000 g
        # custo por kg volta a 45,50 (0,0455/g)
        self.assertAlmostEqual(
            self.carne.custo_unitario * 1000, Decimal('45.50'), places=2)
        self.assertEqual(
            Despesa.objects.filter(origem='ESTOQUE', valor=Decimal('91.00')).count(), 1)

    def test_entrada_sem_valor_nao_salva_e_mostra_erro(self):
        resp = self.client.post(reverse('estoque_ajustar'), {
            'ingrediente': self.carne.id,
            'quantidade': '2',
            'tipo': 'ENTRADA',
            'valor_unitario': '',
            'observacao': '',
        })
        self.assertEqual(resp.status_code, 200)  # re-renderiza, não redireciona
        self.assertContains(resp, 'Não foi possível salvar')
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
