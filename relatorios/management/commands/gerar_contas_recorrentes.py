"""
Gera as contas previstas das despesas recorrentes (água, luz, internet, aluguel,
MEI, feira semanal…) da primeira data de vencimento até o horizonte de cada
frequência.

Pode rodar no boot do servidor (iniciar_servidor.bat) ou por tarefa agendada.
É idempotente — não duplica contas já existentes.

    python manage.py gerar_contas_recorrentes
"""
from django.core.management.base import BaseCommand

from relatorios.views import gerar_despesas_fixas_pendentes


class Command(BaseCommand):
    help = "Gera as contas previstas das despesas recorrentes."

    def add_arguments(self, parser):
        parser.add_argument('--meses', type=int, default=12,
                            help="(compatibilidade) ignorado — o horizonte agora vem da frequência.")

    def handle(self, *args, **options):
        n = gerar_despesas_fixas_pendentes(forcar=True)
        self.stdout.write(self.style.SUCCESS(f"{n} conta(s) prevista(s) gerada(s)."))
