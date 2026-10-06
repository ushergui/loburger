from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from estoque import services as est_services
from estoque.models import MovimentacaoEstoque
from produtos.models import Ingrediente
from relatorios import services as rel_services
from relatorios.models import Despesa
from vendas.models import ConfiguracaoFinanceira

SEM_BACKUP = 'core.management.commands.acertar_inicio.Command._backup'


class AcertarInicioTests(TestCase):
    """Tira do financeiro o barulho da implantação, sem mexer no estoque."""

    def setUp(self):
        ConfiguracaoFinanceira.get_solo()
        self.hoje = timezone.localdate()
        self.carne = Ingrediente.objects.create(
            nome='CARNE', unidade_medida='g', unidade_compra='kg',
            custo_unitario=Decimal('0'), estoque_atual=Decimal('0'))
        # estoque inicial digitado como compra à vista (o erro clássico): 10 kg x R$ 40 = R$ 400
        self.compra = est_services.registrar_compra(
            [{'ingrediente': self.carne, 'quantidade': Decimal('10'), 'valor_unitario': Decimal('40')}],
            'AVISTA', 'Açougue', None)
        # conta futura marcada como paga por engano
        self.luz_futura = Despesa.objects.create(
            descricao='Luz', categoria='ENERGIA', tipo='FIXA', valor=Decimal('450'),
            status='PAGO', data_vencimento=self.hoje + timedelta(days=60), data_pagamento=self.hoje)
        # conta paga em mês anterior
        ant = self.hoje.replace(day=1) - timedelta(days=10)
        self.antiga = Despesa.objects.create(
            descricao='Conserto carro', categoria='VEICULO', tipo='VARIAVEL', valor=Decimal('700'),
            status='PAGO', data_vencimento=ant, data_pagamento=ant)

    def _rodar(self, *extra):
        out = StringIO()
        call_command('acertar_inicio', '--ate', self.hoje.isoformat(), *extra, stdout=out)
        return out.getvalue()

    def test_exige_data_ate(self):
        with self.assertRaises(CommandError):
            call_command('acertar_inicio')

    def test_ensaio_nao_grava_nada(self):
        caixa = rel_services.caixa_acumulado()
        saida = self._rodar()
        self.assertIn('ENSAIO', saida)
        self.assertEqual(Despesa.objects.count(), 3)
        self.assertEqual(rel_services.caixa_acumulado(), caixa)
        self.assertEqual(MovimentacaoEstoque.objects.filter(tipo='ENTRADA').count(), 1)

    def test_aplicar_limpa_financeiro_e_mantem_estoque(self):
        self.assertEqual(rel_services.caixa_acumulado(), Decimal('-1550.00'))  # 400 + 450 + 700
        self.carne.refresh_from_db()
        estoque_antes, custo_antes = self.carne.estoque_atual, self.carne.custo_unitario

        with mock.patch(SEM_BACKUP, return_value='bkp.sqlite3'):
            saida = self._rodar('--sim')
        self.assertIn('APLICADO', saida)

        # A) compra paga some; estoque e custo intactos; entrada vira abertura
        self.assertFalse(Despesa.objects.filter(origem='ESTOQUE').exists())
        self.carne.refresh_from_db()
        self.assertEqual(self.carne.estoque_atual, estoque_antes)
        self.assertEqual(self.carne.custo_unitario, custo_antes)
        mov = MovimentacaoEstoque.objects.get()
        self.assertEqual(mov.tipo, 'ABERTURA')
        self.assertEqual(mov.grupo_compra, '')
        # B) conta futura volta a "a pagar"
        self.luz_futura.refresh_from_db()
        self.assertEqual(self.luz_futura.status, 'PREVISTO')
        self.assertIsNone(self.luz_futura.data_pagamento)
        # C) mês anterior apagado
        self.assertFalse(Despesa.objects.filter(pk=self.antiga.pk).exists())
        self.assertEqual(rel_services.caixa_acumulado(), Decimal('0.00'))

    def test_rodar_de_novo_nao_faz_nada(self):
        with mock.patch(SEM_BACKUP, return_value='bkp'):
            self._rodar('--sim')
            n = Despesa.objects.count()
            self._rodar('--sim')
        self.assertEqual(Despesa.objects.count(), n)

    def test_compra_a_pagar_nao_e_tocada(self):
        """Boleto/cartão ainda a pagar é dívida real: fica, junto com a entrada de estoque."""
        boleto = est_services.registrar_compra(
            [{'ingrediente': self.carne, 'quantidade': Decimal('2'), 'valor_unitario': Decimal('30')}],
            'BOLETO', 'Frigorífico', self.hoje + timedelta(days=10))
        with mock.patch(SEM_BACKUP, return_value='bkp'):
            self._rodar('--sim')
        self.assertTrue(Despesa.objects.filter(pk=boleto.pk, status='PREVISTO').exists())
        self.assertTrue(MovimentacaoEstoque.objects.filter(
            grupo_compra=boleto.grupo_compra, tipo='ENTRADA').exists())
