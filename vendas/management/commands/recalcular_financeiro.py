"""
Recalcula o financeiro de todos os pedidos com a lógica atual (regime de caixa)
e regenera as despesas automáticas dos fechamentos diários.

Use depois de mudar regras de taxa ou ao migrar dados antigos:

    python manage.py recalcular_financeiro
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from vendas.models import Pedido
from vendas.services import sincronizar_despesas_fechamento


class Command(BaseCommand):
    help = "Recalcula valores financeiros de todos os pedidos e regenera despesas de fechamento."

    def handle(self, *args, **options):
        pedidos = Pedido.objects.all()
        total = pedidos.count()
        self.stdout.write(f"Recalculando {total} pedidos...")
        for p in pedidos.iterator():
            p.recalcular_valores_financeiros(save=True)

        # Datas distintas de fechamento diário
        datas = (
            Pedido.objects.filter(cliente_nome__icontains='Fechamento Diário')
            .dates('data_criacao', 'day')
        )
        self.stdout.write(f"Regenerando despesas automáticas de {len(datas)} dias de fechamento...")
        criadas = 0
        for d in datas:
            criadas += sincronizar_despesas_fechamento(d)

        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {total} pedidos recalculados, {criadas} despesas automáticas regeradas."
        ))
