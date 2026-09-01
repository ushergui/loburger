from decimal import Decimal

from django.db import migrations


# Mapa nome-do-canal -> (comissao_base, taxa_online). Casa por "contém", sem
# diferenciar maiúsculas. Canais que não casam ficam com taxa_online = comissao.
REGRAS = [
    ('ifood', Decimal('0.1200'), Decimal('0.1520')),
    ('uai', Decimal('0.0800'), Decimal('0.1150')),   # UaiRango / Uai Rango
    ('aplicativo', Decimal('0.0000'), Decimal('0.0000')),
    ('app', Decimal('0.0000'), Decimal('0.0000')),
    ('proprio', Decimal('0.0000'), Decimal('0.0000')),
    ('próprio', Decimal('0.0000'), Decimal('0.0000')),
]


def ajusta(apps, schema_editor):
    CanalVenda = apps.get_model('vendas', 'CanalVenda')
    for canal in CanalVenda.objects.all():
        nome = (canal.nome or '').lower()
        comissao, online = canal.taxa_comissao, canal.taxa_comissao
        for chave, c, o in REGRAS:
            if chave in nome:
                comissao, online = c, o
                break
        canal.taxa_comissao = comissao
        canal.taxa_online = online
        canal.taxa_fixa = Decimal('0.00')  # iFood/UaiRango não cobram valor fixo por pedido
        canal.save()


def reverte(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('vendas', '0010_remove_configuracaofinanceira_taxa_online_plataforma_and_more'),
    ]

    operations = [
        migrations.RunPython(ajusta, reverte),
    ]
