"""
Tira do financeiro o "barulho" da implantação, SEM apagar cadastros, vendas
reais nem o estoque que já foi contado.

Quando o estoque inicial foi digitado em "Registrar Compra" (ou contas futuras
foram marcadas como pagas por engano), o caixa fica negativo sem motivo. Este
comando acerta isso:

  A) Compras de insumo JÁ PAGAS (feitas pelo carrinho até a data --ate):
     apaga a despesa (não houve saída real de dinheiro) e MANTÉM o estoque;
     as entradas viram "Carga inicial" (ABERTURA).
     Compras ainda PREVISTAS (boleto/cartão a pagar) NÃO são tocadas.
  B) Contas marcadas como PAGAS cujo vencimento é depois da data --ate
     (ex.: Luz e Água de meses que nem chegaram): voltam para PREVISTO.
  C) Contas PAGAS de meses anteriores ao mês da data --ate: apagadas
     ("zerar os meses anteriores"). Contas previstas atrasadas só são listadas.

NÃO muda quantidade nem custo de estoque (use "Contagem de Estoque" na tela).

    python manage.py acertar_inicio --ate 2026-10-06          (só mostra, não grava)
    python manage.py acertar_inicio --ate 2026-10-06 --sim    (faz backup e aplica)

--ate é OBRIGATÓRIO de propósito: tudo lançado até esse dia é tratado como
implantação. Nunca rode de novo depois de começar a lançar compras reais, a não
ser com um --ate anterior ao início dos lançamentos reais.
"""
import os
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from estoque.models import MovimentacaoEstoque
from produtos.models import Ingrediente
from relatorios import services as rel_services
from relatorios.models import Despesa


def _brl(v):
    v = Decimal(v or 0).quantize(Decimal('0.01'))
    s = f"{abs(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


class Command(BaseCommand):
    help = "Remove do financeiro o que foi lançado na implantação (compras de estoque inicial, contas futuras pagas, meses anteriores)."

    def add_arguments(self, parser):
        parser.add_argument('--ate', required=True,
                            help="Data limite da implantação, AAAA-MM-DD (tudo até esse dia é tratado como implantação).")
        parser.add_argument('--sim', action='store_true',
                            help="Aplica de verdade (faz backup antes). Sem isto, só mostra o que faria.")

    # ------------------------------------------------------------------ backup
    def _backup(self):
        db = settings.DATABASES['default']
        if 'sqlite3' not in db['ENGINE']:
            raise CommandError("Backup automático só para SQLite.")
        origem = str(db['NAME'])
        pasta = os.path.dirname(origem)
        nome = f"db_backup_antes_acertar_inicio_{timezone.localtime().strftime('%Y%m%d_%H%M%S')}.sqlite3"
        destino = os.path.join(pasta, nome)
        src = sqlite3.connect(origem)
        dst = sqlite3.connect(destino)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        return destino

    # ------------------------------------------------------------------ regras
    def _aplicar(self, ate, mes_ini):
        """Aplica A, B e C (dentro da transação de quem chamou) e devolve o resumo."""
        r = {}

        # A) compras de insumo já pagas, até a data limite
        compras = Despesa.objects.filter(origem='ESTOQUE', status='PAGO').filter(
            Q(data_referencia__lte=ate) | Q(data_referencia__isnull=True, data_vencimento__lte=ate)
        )
        grupos = set(compras.exclude(grupo_compra='').values_list('grupo_compra', flat=True))
        r['compras_qtd'] = compras.count()
        r['compras_valor'] = compras.aggregate(s=Sum('valor'))['s'] or Decimal('0')
        # entradas que viram carga inicial: as dessas compras + as órfãs (sem grupo) até a data
        grupos_mantidos = set(
            Despesa.objects.filter(origem='ESTOQUE').exclude(status='PAGO')
            .exclude(grupo_compra='').values_list('grupo_compra', flat=True)
        )
        movs = MovimentacaoEstoque.objects.filter(tipo='ENTRADA', data_movimentacao__date__lte=ate)
        movs = movs.filter(Q(grupo_compra__in=grupos) | Q(grupo_compra='')).exclude(grupo_compra__in=grupos_mantidos)
        ids_movs = list(movs.values_list('id', flat=True))
        r['entradas_viram_abertura'] = len(ids_movs)
        for d in compras:
            d.delete()
        MovimentacaoEstoque.objects.filter(id__in=ids_movs).update(
            tipo='ABERTURA', grupo_compra='',
            observacao='Carga inicial (antes lançada como compra).',
        )

        # B) contas pagas com vencimento depois da data limite -> voltam a PREVISTO
        futuras = list(Despesa.objects.filter(status='PAGO', data_vencimento__gt=ate)
                       .exclude(origem__in=['ESTOQUE', 'FECHAMENTO']).order_by('data_vencimento'))
        r['futuras_qtd'] = len(futuras)
        r['futuras_valor'] = sum((d.valor for d in futuras), Decimal('0'))
        r['futuras_lista'] = [f"{d.descricao} {d.data_vencimento:%d/%m/%Y} ({_brl(d.valor)})" for d in futuras]
        for d in futuras:
            d.status = 'PREVISTO'
            d.data_pagamento = None
            d.save()

        # C) contas pagas de meses anteriores -> apagadas
        antigas = list(Despesa.objects.filter(status='PAGO', data_pagamento__lt=mes_ini)
                       .exclude(origem='ESTOQUE').order_by('data_pagamento'))
        r['antigas_qtd'] = len(antigas)
        r['antigas_valor'] = sum((d.valor for d in antigas), Decimal('0'))
        r['antigas_lista'] = [f"{d.descricao} pago em {d.data_pagamento:%d/%m/%Y} ({_brl(d.valor)})" for d in antigas]
        for d in antigas:
            d.delete()

        # só para avisar: previstas já vencidas (não são tocadas)
        atrasadas = Despesa.objects.filter(status='PREVISTO', data_vencimento__lt=ate)
        r['atrasadas_qtd'] = atrasadas.count()
        r['atrasadas_valor'] = atrasadas.aggregate(s=Sum('valor'))['s'] or Decimal('0')
        r['caixa_depois'] = rel_services.caixa_acumulado()
        return r

    # ------------------------------------------------------------------ main
    def handle(self, *args, **options):
        try:
            ate = datetime.strptime(options['ate'], '%Y-%m-%d').date()
        except ValueError:
            raise CommandError("--ate precisa ser uma data AAAA-MM-DD, ex.: 2026-10-06")
        mes_ini = ate.replace(day=1)
        aplicar = options['sim']

        caixa_antes = rel_services.caixa_acumulado()
        valor_estoque = rel_services.valor_estoque_atual()

        backup = self._backup() if aplicar else None

        # No ensaio roda tudo e DESFAZ no final (rollback), para mostrar números reais.
        with transaction.atomic():
            r = self._aplicar(ate, mes_ini)
            if not aplicar:
                transaction.set_rollback(True)

        w = self.stdout.write
        w("")
        w("=" * 64)
        w(("APLICADO" if aplicar else "ENSAIO (nada foi gravado)") + f" - implantação até {ate:%d/%m/%Y}")
        w("=" * 64)
        w(f"A) Compras de insumo já pagas, apagadas das despesas: {r['compras_qtd']}  ({_brl(r['compras_valor'])})")
        w(f"   Entradas de estoque que viram 'Carga inicial': {r['entradas_viram_abertura']}  (o estoque NÃO muda)")
        w(f"B) Contas pagas de meses futuros, voltam a 'a pagar': {r['futuras_qtd']}  ({_brl(r['futuras_valor'])})")
        for linha in r['futuras_lista'][:20]:
            w(f"     - {linha}")
        w(f"C) Contas pagas de meses anteriores a {mes_ini:%m/%Y}, apagadas: {r['antigas_qtd']}  ({_brl(r['antigas_valor'])})")
        for linha in r['antigas_lista'][:20]:
            w(f"     - {linha}")
        w("")
        w(f"Caixa acumulado:  antes {_brl(caixa_antes)}   ->   depois {_brl(r['caixa_depois'])}")
        if r['atrasadas_qtd']:
            w(self.style.WARNING(
                f"Atenção: {r['atrasadas_qtd']} conta(s) 'a pagar' já vencida(s) ({_brl(r['atrasadas_valor'])}) NÃO foram mexidas. "
                "Se forem teste, apague em Custos & Despesas; se forem dívidas reais, deixe."))

        w("")
        w(f"Valor do estoque hoje: {_brl(valor_estoque)}  (este comando não altera estoque).")
        top = sorted(Ingrediente.objects.all(), key=lambda i: -(i.estoque_atual or 0) * (i.custo_unitario or 0))[:6]
        w("Maiores valores em estoque (confira se estão realistas, corrija em 'Contagem de Estoque'):")
        for i in top:
            valor = ((i.estoque_atual or 0) * (i.custo_unitario or 0))
            w(f"     - {i.nome}: {i.estoque_display}  a  {_brl(i.custo_por_unidade_compra)} cada  =  {_brl(valor)}")

        w("")
        if aplicar:
            w(self.style.SUCCESS("Pronto. Backup feito em: " + backup))
        else:
            w(self.style.WARNING("Nada foi gravado. Para aplicar de verdade, rode o mesmo comando com --sim no final."))
