from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from vendas.models import ConfiguracaoFinanceira
from relatorios.models import Despesa, DespesaRecorrente
from relatorios.views import (
    gerar_despesas_fixas_pendentes, propagar_molde_para_previstas,
    contas_a_pagar_urgentes, _rotular_vencimento,
)


class ContasRecorrentesTests(TestCase):
    def setUp(self):
        ConfiguracaoFinanceira.get_solo()
        self.hoje = timezone.localdate()

    def test_molde_gera_faturas_do_mes_e_futuras(self):
        DespesaRecorrente.objects.create(
            descricao='Internet', credor='Vivo', categoria='INTERNET',
            dia_vencimento=15, valor_base=Decimal('120.00'), ativa=True,
        )
        n = gerar_despesas_fixas_pendentes(meses_a_frente=12, forcar=True)
        self.assertEqual(n, 13)  # mês atual + 12
        faturas = Despesa.objects.filter(despesa_matriz__descricao='Internet')
        self.assertTrue(all(f.status == 'PREVISTO' for f in faturas))
        self.assertTrue(all(f.credor == 'Vivo' for f in faturas))
        self.assertTrue(all(f.data_vencimento.day == 15 for f in faturas))

    def test_geracao_e_idempotente_e_1x_por_dia(self):
        DespesaRecorrente.objects.create(
            descricao='Aluguel', categoria='OUTROS', dia_vencimento=5,
            valor_base=Decimal('2000'), ativa=True,
        )
        gerar_despesas_fixas_pendentes(forcar=True)
        antes = Despesa.objects.count()
        # segunda chamada sem forçar: não roda (guarda de 1x/dia)
        n = gerar_despesas_fixas_pendentes()
        self.assertEqual(n, 0)
        self.assertEqual(Despesa.objects.count(), antes)

    def test_editar_molde_realinha_previstas_futuras(self):
        molde = DespesaRecorrente.objects.create(
            descricao='Energia', categoria='ENERGIA', dia_vencimento=10,
            valor_base=Decimal('400'), ativa=True,
        )
        gerar_despesas_fixas_pendentes(forcar=True)
        molde.valor_base = Decimal('480')
        molde.dia_vencimento = 12
        molde.save()
        propagar_molde_para_previstas(molde)
        futuras = Despesa.objects.filter(despesa_matriz=molde, data_vencimento__gte=self.hoje)
        self.assertTrue(all(f.valor == Decimal('480') for f in futuras))
        self.assertTrue(all(f.data_vencimento.day == 12 for f in futuras))

    def test_previstas_nao_afetam_o_caixa(self):
        from relatorios import services
        DespesaRecorrente.objects.create(
            descricao='MEI', categoria='IMPOSTOS', dia_vencimento=20,
            valor_base=Decimal('75'), ativa=True,
        )
        gerar_despesas_fixas_pendentes(forcar=True)
        r = services.resumo_financeiro(self.hoje.replace(day=1), self.hoje)
        self.assertEqual(r['despesas_pagas_total'], Decimal('0.00'))
        self.assertEqual(r['resultado_caixa'], Decimal('0.00'))


class PagamentoContasTests(TestCase):
    def setUp(self):
        ConfiguracaoFinanceira.get_solo()
        self.hoje = timezone.localdate()

    def test_conta_avulsa_com_previsao_e_pagamento_futuro(self):
        """Serviço de manutenção: lanço hoje com previsão para daqui 20 dias,
        confirmo o pagamento nesse dia, e só aí debita do caixa."""
        from relatorios import services
        venc = self.hoje + timedelta(days=20)
        d = Despesa.objects.create(
            descricao='Conserto da chapa', credor='João Refrigeração',
            categoria='MANUTENCAO', tipo='VARIAVEL', valor=Decimal('350'),
            status='PREVISTO', data_vencimento=venc,
        )
        # Enquanto prevista: aparece em contas a pagar, não mexe no caixa do mês do vencimento
        self.assertIn(d, Despesa.objects.filter(status='PREVISTO'))
        r = services.resumo_financeiro(venc.replace(day=1), venc)
        self.assertEqual(r['despesas_pagas_total'], Decimal('0.00'))

        # Confirma pagamento no dia do vencimento
        d.data_pagamento = venc
        d.status = 'PAGO'
        d.save()
        r2 = services.resumo_financeiro(venc.replace(day=1), venc)
        self.assertEqual(r2['despesas_pagas_total'], Decimal('350.00'))
        self.assertEqual(r2['resultado_caixa'], Decimal('-350.00'))

    def test_pagar_debita_no_dia_informado_nao_no_vencimento(self):
        from relatorios import services
        venc = self.hoje.replace(day=1) + timedelta(days=4)   # dia 5
        pago_em = venc + timedelta(days=3)                    # dia 8
        d = Despesa.objects.create(
            descricao='Água', categoria='AGUA_LUZ', valor=Decimal('90'),
            status='PREVISTO', data_vencimento=venc,
        )
        d.data_pagamento = pago_em
        d.status = 'PAGO'
        d.save()
        # período que inclui o vencimento mas não o pagamento
        r = services.resumo_financeiro(venc, venc + timedelta(days=1))
        self.assertEqual(r['despesas_pagas_total'], Decimal('0.00'))
        # período que inclui o pagamento
        r2 = services.resumo_financeiro(pago_em, pago_em)
        self.assertEqual(r2['despesas_pagas_total'], Decimal('90.00'))


class AlertaVencimentoTests(TestCase):
    def setUp(self):
        ConfiguracaoFinanceira.get_solo()
        self.hoje = timezone.localdate()

    def test_urgentes_pega_atrasadas_e_ate_3_dias(self):
        Despesa.objects.create(descricao='Atrasada', categoria='OUTROS', valor=Decimal('10'),
                               status='PREVISTO', data_vencimento=self.hoje - timedelta(days=2))
        Despesa.objects.create(descricao='Hoje', categoria='OUTROS', valor=Decimal('10'),
                               status='PREVISTO', data_vencimento=self.hoje)
        Despesa.objects.create(descricao='Em 3 dias', categoria='OUTROS', valor=Decimal('10'),
                               status='PREVISTO', data_vencimento=self.hoje + timedelta(days=3))
        Despesa.objects.create(descricao='Em 10 dias', categoria='OUTROS', valor=Decimal('10'),
                               status='PREVISTO', data_vencimento=self.hoje + timedelta(days=10))
        Despesa.objects.create(descricao='Já paga', categoria='OUTROS', valor=Decimal('10'),
                               status='PAGO', data_vencimento=self.hoje, data_pagamento=self.hoje)
        urgentes = contas_a_pagar_urgentes(self.hoje)
        self.assertEqual(urgentes.count(), 3)

    def test_rotulos(self):
        d1 = Despesa(data_vencimento=self.hoje - timedelta(days=1))
        d2 = Despesa(data_vencimento=self.hoje)
        d3 = Despesa(data_vencimento=self.hoje + timedelta(days=2))
        _rotular_vencimento(d1, self.hoje)
        _rotular_vencimento(d2, self.hoje)
        _rotular_vencimento(d3, self.hoje)
        self.assertEqual(d1.urgencia, 'atrasada')
        self.assertEqual(d2.urgencia, 'hoje')
        self.assertEqual(d3.urgencia, 'proxima')
