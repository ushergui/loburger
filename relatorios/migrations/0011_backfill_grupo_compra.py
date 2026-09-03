"""Liga as compras antigas (feitas pelo carrinho antes de existir o campo
grupo_compra) às suas movimentações de estoque, para que 'editar' também
reabra o carrinho nelas."""
import re
import uuid
from collections import defaultdict

from django.db import migrations


def backfill(apps, schema_editor):
    Despesa = apps.get_model('relatorios', 'Despesa')
    Mov = apps.get_model('estoque', 'MovimentacaoEstoque')

    for desp in Despesa.objects.filter(origem='ESTOQUE').exclude(grupo_compra__gt=''):
        # quantos itens tinha a nota
        mo = re.search(r'Nota com (\d+)\s*item', desp.observacao or '')
        n_itens = int(mo.group(1)) if mo else None
        # nomes de insumo citados na descrição "Compra xxx: NOME, NOME…"
        md = re.match(r'^Compra [^:]+:\s*(.+)$', desp.descricao or '')
        nomes = set()
        if md:
            nomes = {x.strip().rstrip('…').strip() for x in md.group(1).split(',') if x.strip()}
        ref = desp.data_referencia or desp.data_vencimento

        candidatas = Mov.objects.filter(tipo='ENTRADA', grupo_compra='')
        if ref:
            candidatas = candidatas.filter(data_movimentacao__date=ref)
        candidatas = list(candidatas.select_related('ingrediente'))
        if not candidatas:
            continue

        # movimentações da mesma compra compartilham o mesmo instante (loop de criação)
        clusters = defaultdict(list)
        for mv in candidatas:
            clusters[mv.data_movimentacao.replace(microsecond=0)].append(mv)

        escolhido = None
        for _, grp in sorted(clusters.items()):
            grp_nomes = {mv.ingrediente.nome for mv in grp}
            tam_ok = (n_itens is None) or (len(grp) == n_itens)
            nomes_ok = (not nomes) or nomes.issubset(grp_nomes)
            if tam_ok and nomes_ok:
                escolhido = grp
                break
        if escolhido is None:
            continue

        grupo = uuid.uuid4().hex
        desp.grupo_compra = grupo
        desp.save(update_fields=['grupo_compra'])
        for mv in escolhido:
            mv.grupo_compra = grupo
            mv.save(update_fields=['grupo_compra'])


class Migration(migrations.Migration):

    dependencies = [
        ('relatorios', '0010_despesa_grupo_compra'),
        ('estoque', '0006_movimentacaoestoque_custo_medio_antes_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
