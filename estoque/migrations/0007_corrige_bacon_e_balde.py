"""Correção pontual de dados da implantação (pedida pela gestão).

1) BACON: apaga do histórico o par lançado por engano em 05/10 — a carga inicial de
   98 kg (ABERTURA, sem observação) e a saída de 196 kg por autoconsumo marcada
   "cadastro errado". Só remove as linhas do HISTÓRICO: o estoque atual do bacon NÃO
   é alterado (a quantidade certa se acerta em "Contagem de Estoque").
2) BALDE DE MANTEIGA: estava como medida "ml" e compra "kg" (cadastro torto). São 3
   baldes comprados a R$ 142 cada (nota de R$ 426), então as duas unidades viram "un".
   Estoque e custo ficam como estão.

É segura em qualquer banco: só age se encontrar exatamente esses registros; se não
encontrar (outro banco, ou já corrigido), não faz nada.
"""
from decimal import Decimal

from django.db import migrations
from django.db.models import Q


def corrigir(apps, schema_editor):
    Ingrediente = apps.get_model('produtos', 'Ingrediente')
    Mov = apps.get_model('estoque', 'MovimentacaoEstoque')

    # 1) par errado do bacon
    for bacon in Ingrediente.objects.filter(nome='BACON'):
        saida = Mov.objects.filter(
            ingrediente=bacon, tipo='SAIDA_AUTOCONSUMO',
            quantidade=Decimal('196000'), observacao='cadastro errado',
        )
        if not saida.exists():
            continue  # sem a saída errada, não mexe em nada (nem na abertura)
        Mov.objects.filter(
            ingrediente=bacon, tipo='ABERTURA', quantidade=Decimal('98000'),
        ).filter(Q(observacao='') | Q(observacao__isnull=True)).delete()
        saida.delete()

    # 2) balde de manteiga: unidades coerentes
    Ingrediente.objects.filter(
        nome='BALDE DE MANTEIGA', unidade_medida='ml', unidade_compra='kg',
    ).update(unidade_medida='un', unidade_compra='un')


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0006_movimentacaoestoque_custo_medio_antes_and_more'),
        ('produtos', '0007_alter_produto_categoria'),
    ]

    operations = [
        migrations.RunPython(corrigir, migrations.RunPython.noop),
    ]
