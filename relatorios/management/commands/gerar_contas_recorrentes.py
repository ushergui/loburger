"""
Gera as faturas previstas dos moldes de despesa fixa (água, luz, internet,
aluguel, MEI…) para o mês atual e os próximos meses.

Pode rodar no boot do servidor (iniciar_servidor.bat) ou por uma tarefa
agendada. É idempotente — não duplica faturas já existentes.

    python manage.py gerar_contas_recorrentes
"""
from django.core.management.base import BaseCommand

from relatorios.views import gerar_despesas_fixas_pendentes


class Command(BaseCommand):
    help = "Gera as faturas previstas dos moldes de despesa fixa (recorrentes)."

    def add_arguments(self, parser):
        parser.add_argument('--meses', type=int, default=12, help="Quantos meses à frente projetar.")

    def handle(self, *args, **options):
        n = gerar_despesas_fixas_pendentes(meses_a_frente=options['meses'], forcar=True)
        self.stdout.write(self.style.SUCCESS(f"{n} fatura(s) prevista(s) gerada(s)."))
