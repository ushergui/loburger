"""
Apaga os dados de MOVIMENTO (vendas, despesas, movimentações de estoque,
entregas) e mantém os CADASTROS (ingredientes, produtos, fichas técnicas,
preços, canais, configuração, usuários).

O estoque de cada insumo volta a zero — a quantidade real é lançada depois
como "Carga Inicial / Abertura".

    python manage.py limpar_dados_operacionais --confirmar
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Zera os dados de movimento (vendas, despesas, estoque movido) mantendo os cadastros."

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true', help="Confirma a operação (destrutiva).")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirmar']:
            self.stdout.write(self.style.WARNING(
                "Operação destrutiva. Rode de novo com --confirmar para executar."
            ))
            return

        from vendas.models import Pedido, PedidoItem, EntregaDiaria, Entregador, FechamentoDiarioInfo
        from estoque.models import MovimentacaoEstoque
        from relatorios.models import Despesa, DespesaRecorrente
        from produtos.models import Ingrediente

        contagem = {
            'itens de pedido': PedidoItem.objects.count(),
            'pedidos': Pedido.objects.count(),
            'movimentações de estoque': MovimentacaoEstoque.objects.count(),
            'entregas do dia': EntregaDiaria.objects.count(),
            'entregadores': Entregador.objects.count(),
            'despesas': Despesa.objects.count(),
            'moldes de despesa fixa': DespesaRecorrente.objects.count(),
            'fechamentos diários': FechamentoDiarioInfo.objects.count(),
        }

        PedidoItem.objects.all().delete()
        Pedido.objects.all().delete()
        MovimentacaoEstoque.objects.all().delete()
        EntregaDiaria.objects.all().delete()
        Entregador.objects.all().delete()
        Despesa.objects.all().delete()
        DespesaRecorrente.objects.all().delete()
        FechamentoDiarioInfo.objects.all().delete()

        atualizados = Ingrediente.objects.exclude(estoque_atual=Decimal('0')).update(estoque_atual=Decimal('0'))

        for nome, n in contagem.items():
            self.stdout.write(f"  - {nome}: {n} apagados")
        self.stdout.write(f"  - estoque de {atualizados} insumos zerado")
        self.stdout.write(self.style.SUCCESS(
            "Pronto. Cadastros (insumos, cardápio, fichas, preços, canais, config, usuários) mantidos."
        ))
