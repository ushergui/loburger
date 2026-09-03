"""
Deixa o banco pronto para o Igor começar a usar DE VERDADE.

Mantém tudo que é cadastro (ingredientes com o preço de referência, cardápio,
fichas técnicas, adicionais, preços por canal, canais, entregadores, usuários,
configuração de taxas) e APAGA tudo que é movimento/simulação:

  - movimentações de estoque   -> zera o estoque de todo insumo
  - pedidos e entregas do dia
  - despesas (avulsas, de fechamento, de estoque)
  - moldes de contas fixas (eles vão cadastrar os reais)
  - histórico de auditoria (o "barulho" das cargas)

NÃO mexe em custo_unitario dos insumos (é a referência de mercado).

    python manage.py preparar_base_real
    python manage.py preparar_base_real --sim   (confirma de verdade)
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from produtos.models import Ingrediente
from estoque.models import MovimentacaoEstoque
from vendas.models import Pedido, EntregaDiaria, ConfiguracaoFinanceira
from relatorios.models import Despesa, DespesaRecorrente

try:
    from core.models import LogAuditoria
except Exception:  # pragma: no cover
    LogAuditoria = None


class Command(BaseCommand):
    help = "Zera movimentos/simulação e deixa o banco pronto para uso real (mantém os cadastros)."

    def add_arguments(self, parser):
        parser.add_argument('--sim', action='store_true',
                            help="Confirma a limpeza (sem isto, só mostra o que faria).")

    @transaction.atomic
    def handle(self, *args, **options):
        resumo = {
            'Movimentações de estoque': MovimentacaoEstoque.objects.count(),
            'Pedidos': Pedido.objects.count(),
            'Entregas do dia': EntregaDiaria.objects.count(),
            'Despesas': Despesa.objects.count(),
            'Moldes de contas fixas': DespesaRecorrente.objects.count(),
            'Insumos com estoque > 0': Ingrediente.objects.filter(estoque_atual__gt=0).count(),
        }
        if LogAuditoria is not None:
            resumo['Registros de auditoria'] = LogAuditoria.objects.count()

        self.stdout.write("\nO que será apagado / zerado:")
        for k, v in resumo.items():
            self.stdout.write(f"  - {k}: {v}")

        if not options['sim']:
            self.stdout.write(self.style.WARNING(
                "\nNada foi alterado. Rode de novo com --sim para confirmar."))
            return

        MovimentacaoEstoque.objects.all().delete()
        Pedido.objects.all().delete()
        EntregaDiaria.objects.all().delete()
        Despesa.objects.all().delete()
        DespesaRecorrente.objects.all().delete()
        if LogAuditoria is not None:
            LogAuditoria.objects.all().delete()

        Ingrediente.objects.update(
            estoque_atual=Decimal('0'), estoque_minimo=Decimal('0'))

        cfg = ConfiguracaoFinanceira.get_solo()
        cfg.caixa_inicial = Decimal('0')
        cfg.ultima_geracao_recorrentes = None
        cfg.save()

        self.stdout.write(self.style.SUCCESS(
            "\nBase pronta para uso real. Cadastros preservados, estoque zerado, "
            "sem pedidos/despesas/histórico. Comece pelo tutorial (Primeiros Passos)."))
