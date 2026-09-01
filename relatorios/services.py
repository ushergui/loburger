"""
Consolidação financeira do LOL BURGUER.

Regime de caixa: o custo do insumo é reconhecido na COMPRA (entrada de estoque
gera Despesa FORNECEDORES). A venda entra no caixa pelo valor líquido
(faturamento - comissão do canal - taxa de pagamento - desconto).

Para não contar as taxas duas vezes, as Despesas automáticas de categoria
TAXA_PLATAFORMA e TAXA_MAQUININHA existem apenas para visibilidade em
"Custos & Despesas" e NÃO entram de novo no resultado de caixa.
"""
from decimal import Decimal
from django.db.models import Sum, Count

TAXAS_JA_EMBUTIDAS = ('TAXA_PLATAFORMA', 'TAXA_MAQUININHA')


def _z(v):
    return v if v is not None else Decimal('0.00')


def valor_estoque_atual():
    """Valor do estoque hoje = soma de (estoque atual x custo médio) de cada insumo."""
    from produtos.models import Ingrediente
    total = Decimal('0.00')
    for ing in Ingrediente.objects.all():
        total += (ing.estoque_atual or Decimal('0')) * (ing.custo_unitario or Decimal('0'))
    return total.quantize(Decimal('0.01'))


def receita_entregas(d_ini, d_fim):
    """Dinheiro de taxa de entrega cobrado dos clientes no período."""
    from vendas.models import EntregaDiaria, ConfiguracaoFinanceira
    config = ConfiguracaoFinanceira.get_solo()
    qtd = EntregaDiaria.objects.filter(data__gte=d_ini, data__lte=d_fim).aggregate(s=Sum('quantidade'))['s'] or 0
    return (Decimal(qtd) * config.taxa_entrega).quantize(Decimal('0.01'))


def resumo_financeiro(d_ini, d_fim):
    """Retorna o dicionário de KPIs do período [d_ini, d_fim] (datas)."""
    from vendas.models import Pedido
    from relatorios.models import Despesa, CATEGORIAS_NAO_OPERACIONAIS

    pedidos = Pedido.objects.filter(
        status='CONCLUIDO',
        data_criacao__date__gte=d_ini,
        data_criacao__date__lte=d_fim,
    )
    agg = pedidos.aggregate(
        bruto=Sum('valor_bruto'),
        taxas_canal=Sum('taxas_canal'),
        taxas_pgto=Sum('taxas_pagamento'),
        cmv=Sum('custo_ingredientes'),
        liquido=Sum('lucro_liquido'),
        n=Count('id'),
    )
    bruto = _z(agg['bruto'])
    taxas_canal = _z(agg['taxas_canal'])
    taxas_pgto = _z(agg['taxas_pgto'])
    cmv = _z(agg['cmv'])
    liquido = _z(agg['liquido'])
    n_pedidos = agg['n'] or 0

    rec_entregas = receita_entregas(d_ini, d_fim)

    despesas_qs = Despesa.objects.filter(
        status='PAGO', data_pagamento__gte=d_ini, data_pagamento__lte=d_fim,
    )
    despesas_total = _z(despesas_qs.aggregate(s=Sum('valor'))['s'])
    retiradas = _z(despesas_qs.filter(categoria__in=CATEGORIAS_NAO_OPERACIONAIS).aggregate(s=Sum('valor'))['s'])
    compras_insumo = _z(despesas_qs.filter(categoria='FORNECEDORES').aggregate(s=Sum('valor'))['s'])
    # Saídas de caixa: tudo que foi pago, menos as taxas que já estão embutidas no líquido.
    saidas_caixa = _z(despesas_qs.exclude(categoria__in=TAXAS_JA_EMBUTIDAS).aggregate(s=Sum('valor'))['s'])

    entradas_caixa = liquido + rec_entregas
    resultado_caixa = entradas_caixa - saidas_caixa
    # Antes das retiradas dos sócios (o que a operação gerou de fato)
    resultado_operacional = resultado_caixa + retiradas
    # Ponte para competência: devolve o que virou estoque, tira o que saiu do estoque
    lucro_economico = resultado_operacional + compras_insumo - cmv

    ticket = (bruto / n_pedidos) if n_pedidos else Decimal('0.00')

    return {
        'faturamento_bruto': bruto,
        'num_pedidos': n_pedidos,
        'ticket_medio': ticket.quantize(Decimal('0.01')),
        'taxas_plataforma': taxas_canal + taxas_pgto,
        'cmv': cmv,
        'receita_entregas': rec_entregas,
        'compras_insumo': compras_insumo,
        'despesas_pagas_total': despesas_total,
        'retiradas_socios': retiradas,
        'entradas_caixa': entradas_caixa.quantize(Decimal('0.01')),
        'saidas_caixa': saidas_caixa.quantize(Decimal('0.01')),
        'resultado_caixa': resultado_caixa.quantize(Decimal('0.01')),
        'resultado_operacional': resultado_operacional.quantize(Decimal('0.01')),
        'lucro_economico': lucro_economico.quantize(Decimal('0.01')),
    }


def caixa_acumulado(ate_data=None):
    """Saldo de caixa acumulado (a 'foto', não zera no mês).

    = caixa inicial + tudo que a operação recebeu - tudo que foi pago
    (exceto as taxas, que já estão embutidas no líquido das vendas).
    """
    from vendas.models import Pedido, EntregaDiaria, ConfiguracaoFinanceira
    from relatorios.models import Despesa
    config = ConfiguracaoFinanceira.get_solo()

    ped = Pedido.objects.filter(status='CONCLUIDO')
    ent = EntregaDiaria.objects.all()
    desp = Despesa.objects.filter(status='PAGO').exclude(categoria__in=TAXAS_JA_EMBUTIDAS)
    if ate_data is not None:
        ped = ped.filter(data_criacao__date__lte=ate_data)
        ent = ent.filter(data__lte=ate_data)
        desp = desp.filter(data_pagamento__lte=ate_data)

    liquido = _z(ped.aggregate(s=Sum('lucro_liquido'))['s'])
    qtd_ent = ent.aggregate(s=Sum('quantidade'))['s'] or 0
    rec_ent = Decimal(qtd_ent) * config.taxa_entrega
    saidas = _z(desp.aggregate(s=Sum('valor'))['s'])

    return (config.caixa_inicial + liquido + rec_ent - saidas).quantize(Decimal('0.01'))


def resumo_movimentacao_estoque(d_ini, d_fim):
    """Autoconsumo e perdas do período, valorizados pelo custo."""
    from estoque.models import MovimentacaoEstoque
    movs = MovimentacaoEstoque.objects.filter(
        data_movimentacao__date__gte=d_ini, data_movimentacao__date__lte=d_fim,
    ).select_related('ingrediente')
    autoconsumo = Decimal('0.00')
    perdas = Decimal('0.00')
    for m in movs:
        if m.tipo == 'SAIDA_AUTOCONSUMO':
            autoconsumo += m.valor_movimento
        elif m.tipo == 'SAIDA_PERDA':
            perdas += m.valor_movimento
    return {'autoconsumo': autoconsumo, 'perdas': perdas}
