"""
Serviços do módulo de vendas.

sincronizar_despesas_fechamento(data): recria, para um dia, as Despesas
automáticas geradas pelo fechamento diário — taxas das plataformas, taxa da
maquininha e pagamento dos entregadores. É idempotente: apaga as anteriores
daquele dia e cria de novo a partir dos pedidos e entregas gravados.
"""
from decimal import Decimal
from django.db.models import Sum


def sincronizar_despesas_fechamento(data):
    from relatorios.models import Despesa
    from .models import Pedido, EntregaDiaria, ConfiguracaoFinanceira

    config = ConfiguracaoFinanceira.get_solo()
    data_fmt = data.strftime('%d/%m/%Y')

    # 1. Limpa as despesas automáticas anteriores deste dia
    Despesa.objects.filter(origem='FECHAMENTO', data_referencia=data).delete()

    pedidos = Pedido.objects.filter(status='CONCLUIDO', data_criacao__date=data).select_related('canal')

    novas = []

    # 2. Taxa de plataforma por canal + taxa da maquininha (na entrega, no cartão)
    por_canal = {}
    taxa_maquininha_total = Decimal('0.00')
    for p in pedidos:
        por_canal[p.canal] = por_canal.get(p.canal, Decimal('0.00')) + p.taxas_canal
        taxa_maquininha_total += p.taxas_pagamento

    for canal, valor in por_canal.items():
        if valor > 0:
            novas.append(Despesa(
                descricao=f"Taxa {canal.nome} — {data_fmt}",
                tipo='VARIAVEL', categoria='TAXA_PLATAFORMA', valor=valor.quantize(Decimal('0.01')),
                status='PAGO', data_vencimento=data, data_pagamento=data,
                origem='FECHAMENTO', data_referencia=data,
                observacao="Gerada automaticamente pelo fechamento diário.",
            ))

    if taxa_maquininha_total > 0:
        novas.append(Despesa(
            descricao=f"Taxa da maquininha — {data_fmt}",
            tipo='VARIAVEL', categoria='TAXA_MAQUININHA', valor=taxa_maquininha_total.quantize(Decimal('0.01')),
            status='PAGO', data_vencimento=data, data_pagamento=data,
            origem='FECHAMENTO', data_referencia=data,
            observacao="Gerada automaticamente pelo fechamento diário.",
        ))

    # 3. Pagamento dos entregadores (exceto sócios)
    for e in EntregaDiaria.objects.filter(data=data).select_related('entregador'):
        if e.quantidade > 0 and not e.entregador.eh_socio:
            valor = (Decimal(e.quantidade) * config.taxa_entrega).quantize(Decimal('0.01'))
            novas.append(Despesa(
                descricao=f"Motoboy — {e.entregador.nome} ({e.quantidade}x) — {data_fmt}",
                tipo='VARIAVEL', categoria='ENTREGA', valor=valor,
                status='PAGO', data_vencimento=data, data_pagamento=data,
                origem='FECHAMENTO', data_referencia=data,
                observacao="Gerada automaticamente pelo fechamento diário.",
            ))

    Despesa.objects.bulk_create(novas)
    return len(novas)
