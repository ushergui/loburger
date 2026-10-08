"""
Serviços do módulo de vendas.

sincronizar_despesas_fechamento(data): mantém, para um dia, as Despesas
automáticas geradas pelo fechamento diário — taxas das plataformas, taxa da
maquininha e pagamento dos entregadores. É idempotente e só mexe no que
mudou (cria o que falta, corrige o valor, apaga o que sobrou).

salvar_*_fechamento(...): salvamento CÉLULA A CÉLULA do Fechamento Diário (a tela
grava sozinha cada campo, como uma planilha). Cada função grava só aquele campo,
ajusta o estoque pela DIFERENÇA e devolve o resumo do dia.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

PREFIXO_FECHAMENTO = 'Fechamento Diário'
QTD_MAXIMA = 9999


class FechamentoErro(ValueError):
    """Entrada inválida no salvamento do fechamento (vira mensagem para a pessoa)."""


def sincronizar_despesas_fechamento(data):
    from relatorios.models import Despesa
    from .models import Pedido, EntregaDiaria, ConfiguracaoFinanceira

    config = ConfiguracaoFinanceira.get_solo()
    data_fmt = data.strftime('%d/%m/%Y')

    pedidos = Pedido.objects.filter(status='CONCLUIDO', data_criacao__date=data).select_related('canal')

    # descrição -> (categoria, valor): o que DEVE existir neste dia
    desejadas = {}

    # 1. Taxa de plataforma por canal + taxa da maquininha (na entrega, no cartão)
    por_canal = {}
    taxa_maquininha_total = Decimal('0.00')
    for p in pedidos:
        por_canal[p.canal] = por_canal.get(p.canal, Decimal('0.00')) + p.taxas_canal
        taxa_maquininha_total += p.taxas_pagamento

    for canal, valor in por_canal.items():
        if valor > 0:
            desejadas[f"Taxa {canal.nome} — {data_fmt}"] = ('TAXA_PLATAFORMA', valor.quantize(Decimal('0.01')))

    if taxa_maquininha_total > 0:
        desejadas[f"Taxa da maquininha — {data_fmt}"] = ('TAXA_MAQUININHA', taxa_maquininha_total.quantize(Decimal('0.01')))

    # 2. Pagamento dos entregadores (exceto sócios)
    for e in EntregaDiaria.objects.filter(data=data).select_related('entregador'):
        if e.quantidade > 0 and not e.entregador.eh_socio:
            valor = (Decimal(e.quantidade) * config.taxa_entrega).quantize(Decimal('0.01'))
            desejadas[f"Motoboy — {e.entregador.nome} ({e.quantidade}x) — {data_fmt}"] = ('ENTREGA', valor)

    # 3. Compara com o que já existe e só mexe na diferença (evita apagar e recriar a cada
    #    digitação — o histórico de auditoria ficaria cheio de ruído).
    existentes = {}
    sobras = []
    for d in Despesa.objects.filter(origem='FECHAMENTO', data_referencia=data).order_by('id'):
        if d.descricao in existentes:
            sobras.append(d)          # duplicada: não deveria existir
        else:
            existentes[d.descricao] = d

    novas = []
    for descricao, (categoria, valor) in desejadas.items():
        atual = existentes.pop(descricao, None)
        if atual is None:
            novas.append(Despesa(
                descricao=descricao, tipo='VARIAVEL', categoria=categoria, valor=valor,
                status='PAGO', data_vencimento=data, data_pagamento=data,
                origem='FECHAMENTO', data_referencia=data,
                observacao="Gerada automaticamente pelo fechamento diário.",
            ))
        elif atual.valor != valor or atual.categoria != categoria or atual.status != 'PAGO':
            atual.valor, atual.categoria, atual.status = valor, categoria, 'PAGO'
            atual.data_pagamento = data
            atual.save()

    for d in list(existentes.values()) + sobras:
        d.delete()
    Despesa.objects.bulk_create(novas)
    return len(desejadas)


# ======================================================================
# Salvamento célula a célula
# ======================================================================

def _pedidos_fechamento(data):
    from .models import Pedido
    return Pedido.objects.filter(
        data_criacao__date=data, status='CONCLUIDO', cliente_nome__icontains=PREFIXO_FECHAMENTO,
    )


def _info_do_dia(data):
    """FechamentoDiarioInfo do dia (criado se não existir). Dia antigo (desconto nulo)
    herda o desconto que estava gravado nos pedidos."""
    from .models import FechamentoDiarioInfo, ConfiguracaoFinanceira
    info, _ = FechamentoDiarioInfo.objects.get_or_create(
        data=data, defaults={'quantidade_entregas': 0, 'taxa_entrega': ConfiguracaoFinanceira.get_solo().taxa_entrega},
    )
    if info.desconto_dia is None:
        info.desconto_dia = max((p.desconto for p in _pedidos_fechamento(data)), default=Decimal('0.00'))
        info.save(update_fields=['desconto_dia'])
    return info


def desconto_do_dia_leitura(data):
    """Para mostrar na tela (não cria nada)."""
    from .models import FechamentoDiarioInfo
    info = FechamentoDiarioInfo.objects.filter(data=data).first()
    if info is not None and info.desconto_dia is not None:
        return info.desconto_dia
    return max((p.desconto for p in _pedidos_fechamento(data)), default=Decimal('0.00'))


def _reaplicar_desconto(data):
    """O desconto do dia vale uma vez só: fica no primeiro pedido do dia, os demais zerados."""
    from .models import Pedido
    desconto = _info_do_dia(data).desconto_dia or Decimal('0.00')
    for i, ped in enumerate(_pedidos_fechamento(data).order_by('id')):
        alvo = desconto if i == 0 else Decimal('0.00')
        if ped.desconto != alvo:
            Pedido.objects.filter(id=ped.id).update(desconto=alvo)
            ped.desconto = alvo
            ped.recalcular_valores_financeiros(save=True)


def _mexer_estoque(produto, delta, pedido, responsavel=None):
    """delta > 0: mais vendas -> baixa os insumos da ficha; delta < 0: devolve ao estoque."""
    from estoque.models import MovimentacaoEstoque
    if delta == 0:
        return
    for ingrediente, qtd in produto.insumos_consolidados(abs(delta)).values():
        if delta > 0:
            ingrediente.estoque_atual -= qtd
            tipo = 'SAIDA_VENDA'
            obs = f"Baixa do fechamento: +{delta}x {produto.nome} (Pedido #{pedido.id})"
        else:
            ingrediente.estoque_atual += qtd
            tipo = 'AJUSTE'
            obs = f"Estorno do fechamento: -{abs(delta)}x {produto.nome} (Pedido #{pedido.id})"
        ingrediente.save()
        MovimentacaoEstoque.objects.create(
            ingrediente=ingrediente, quantidade=qtd, tipo=tipo, observacao=obs, responsavel=responsavel,
        )


def resumo_do_dia(data):
    pedidos = list(_pedidos_fechamento(data))
    bruto = sum((p.valor_bruto for p in pedidos), Decimal('0.00'))
    liquido = sum((p.lucro_liquido for p in pedidos), Decimal('0.00'))
    return {'total_bruto': f"{bruto:.2f}", 'total_liquido': f"{liquido:.2f}", 'pedidos': len(pedidos)}


def _inteiro(valor, nome):
    texto = (str(valor) if valor is not None else '').strip()
    if texto == '':
        return 0
    if not texto.isdigit():
        raise FechamentoErro(f"{nome}: digite só números inteiros (sem vírgula nem sinal).")
    n = int(texto)
    if n > QTD_MAXIMA:
        raise FechamentoErro(f"{nome}: o máximo é {QTD_MAXIMA}.")
    return n


def salvar_celula_fechamento(data, produto_id, canal_id, modo, quantidade, responsavel=None):
    """Grava UMA célula (produto x canal x forma de pagamento) do fechamento do dia.
    A quantidade digitada é o total daquela célula (0 = tirar)."""
    from produtos.models import Produto, PrecoCanal
    from .models import Pedido, PedidoItem, CanalVenda

    modos = dict(Pedido.MODO_PAGAMENTO_CHOICES)
    if modo not in modos:
        raise FechamentoErro("Forma de pagamento inválida.")
    qtd = _inteiro(quantidade, "Quantidade")
    produto = Produto.objects.filter(id=produto_id).first()
    canal = CanalVenda.objects.filter(id=canal_id).first()
    if produto is None or canal is None:
        raise FechamentoErro("Produto ou canal não encontrado. Recarregue a página.")

    sem_preco = False
    with transaction.atomic():
        ped = _pedidos_fechamento(data).filter(canal=canal, modo_pagamento=modo).order_by('id').first()
        item = PedidoItem.objects.filter(pedido=ped, produto=produto).first() if ped else None
        antiga = item.quantidade if item else 0
        delta = qtd - antiga

        if delta != 0:
            if ped is None:
                ped = Pedido.objects.create(
                    cliente_nome=f"{PREFIXO_FECHAMENTO} ({modos[modo]})",
                    canal=canal, modo_pagamento=modo, status='CONCLUIDO',
                )
                # data_criacao é auto_now_add — força a data do fechamento. O estoque deste pedido é
                # controlado item a item (por esta função), então já nasce como "baixado".
                Pedido.objects.filter(id=ped.id).update(
                    data_criacao=timezone.make_aware(datetime.combine(data, datetime.now().time())),
                    estoque_baixado=True,
                )
                ped.refresh_from_db()

            preco_tab = PrecoCanal.objects.filter(produto=produto, canal=canal).values_list('preco', flat=True).first()
            preco = preco_tab if preco_tab is not None else (item.preco_unitario if item else Decimal('0.00'))
            sem_preco = qtd > 0 and preco <= 0

            if qtd > 0:
                if item is None:
                    PedidoItem.objects.create(pedido=ped, produto=produto, quantidade=qtd, preco_unitario=preco)
                else:
                    item.quantidade, item.preco_unitario = qtd, preco
                    item.save()
            else:
                item.delete()

            _mexer_estoque(produto, delta, ped, responsavel)

            if ped.itens.exists():
                ped.recalcular_valores_financeiros(save=True)
            else:
                ped.delete()            # pedido ficou vazio: some (o estoque já foi devolvido acima)
            _reaplicar_desconto(data)
            sincronizar_despesas_fechamento(data)
        else:
            if qtd > 0:
                sem_preco = not PrecoCanal.objects.filter(produto=produto, canal=canal, preco__gt=0).exists()

    return {'qtd': qtd, 'sem_preco': sem_preco, **resumo_do_dia(data)}


def salvar_entrega_fechamento(data, entregador_id, quantidade):
    from .models import Entregador, EntregaDiaria, ConfiguracaoFinanceira
    qtd = _inteiro(quantidade, "Entregas")
    entregador = Entregador.objects.filter(id=entregador_id).first()
    if entregador is None:
        raise FechamentoErro("Entregador não encontrado. Recarregue a página.")
    with transaction.atomic():
        EntregaDiaria.objects.update_or_create(data=data, entregador=entregador, defaults={'quantidade': qtd})
        info = _info_do_dia(data)
        info.quantidade_entregas = EntregaDiaria.objects.filter(data=data).aggregate(s=Sum('quantidade'))['s'] or 0
        info.taxa_entrega = ConfiguracaoFinanceira.get_solo().taxa_entrega
        info.save(update_fields=['quantidade_entregas', 'taxa_entrega'])
        sincronizar_despesas_fechamento(data)
    return {'qtd': qtd, **resumo_do_dia(data)}


def salvar_desconto_fechamento(data, valor):
    from core.utils import parse_numero_ptbr
    texto = (str(valor) if valor is not None else '').strip()
    v = parse_numero_ptbr(texto, Decimal('0')) if texto else Decimal('0')
    try:
        v = Decimal(v).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise FechamentoErro("Desconto inválido.")
    if v < 0:
        raise FechamentoErro("O desconto não pode ser negativo.")
    with transaction.atomic():
        info = _info_do_dia(data)
        info.desconto_dia = v
        info.save(update_fields=['desconto_dia'])
        _reaplicar_desconto(data)
        sincronizar_despesas_fechamento(data)
    return {'valor': f"{v:.2f}", **resumo_do_dia(data)}
