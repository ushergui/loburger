"""Regras de entrada de estoque: conversão de unidade, custo médio ponderado
e (para compras) a despesa única da nota."""
import uuid
from decimal import Decimal

from django.utils import timezone

from produtos.models import Ingrediente
from .models import MovimentacaoEstoque

FORMA_CURTA = {'AVISTA': 'à vista', 'CARTAO': 'cartão', 'BOLETO': 'boleto', 'OUTRO': 'compra'}


def aplicar_entrada(ingrediente, qtd_compra, custo_compra_unit, tipo='ENTRADA',
                    responsavel=None, observacao='', grupo_compra=''):
    """Soma `qtd_compra` (na unidade de COMPRA) ao estoque de `ingrediente`,
    recalcula o custo médio ponderado e registra a movimentação.
    NÃO gera despesa — quem cuida disso é quem chama.
    Retorna (movimentacao, valor_total_na_unidade_de_compra)."""
    qtd_compra = Decimal(str(qtd_compra))
    custo_compra_unit = Decimal(str(custo_compra_unit or 0))
    fator = ingrediente.obter_fator_conversao

    qtd_consumo = qtd_compra * fator
    custo_consumo = (custo_compra_unit / fator) if custo_compra_unit > 0 else Decimal('0')
    custo_medio_antes = ingrediente.custo_unitario or Decimal('0')

    if custo_consumo > 0:
        anterior = ingrediente.estoque_atual or Decimal('0')
        if anterior > 0:
            total_ant = anterior * custo_medio_antes
            total_novo = qtd_consumo * custo_consumo
            ingrediente.custo_unitario = (total_ant + total_novo) / (anterior + qtd_consumo)
        else:
            ingrediente.custo_unitario = custo_consumo

    ingrediente.estoque_atual = (ingrediente.estoque_atual or Decimal('0')) + qtd_consumo
    ingrediente.save()

    mov = MovimentacaoEstoque.objects.create(
        ingrediente=ingrediente,
        quantidade=qtd_consumo,
        tipo=tipo,
        valor_unitario=custo_consumo,
        responsavel=responsavel,
        observacao=observacao or '',
        grupo_compra=grupo_compra,
        custo_medio_antes=custo_medio_antes,
    )
    return mov, (qtd_compra * custo_compra_unit)


def registrar_compra(itens, forma_pagamento, credor, data_vencimento,
                     descricao='', responsavel=None):
    """`itens` = lista de dicts {ingrediente, quantidade, valor_unitario} (unidade de COMPRA).
    Dá entrada de cada item e cria UMA despesa para o total da nota.
    - AVISTA  -> despesa PAGA hoje
    - CARTAO/BOLETO -> despesa PREVISTA com o vencimento informado
    Retorna a Despesa criada."""
    from relatorios.models import Despesa, tipo_por_categoria

    hoje = timezone.localdate()
    forma_curta = FORMA_CURTA.get(forma_pagamento, 'compra')
    grupo = uuid.uuid4().hex
    total = Decimal('0.00')
    nomes = []
    for item in itens:
        ing = item['ingrediente']
        mov, valor = aplicar_entrada(
            ing, item['quantidade'], item['valor_unitario'],
            tipo='ENTRADA', responsavel=responsavel,
            observacao=f"Compra {forma_curta}.",
            grupo_compra=grupo,
        )
        total += valor
        nomes.append(ing.nome)

    total = total.quantize(Decimal('0.01'))
    resumo = ', '.join(nomes[:4]) + ('…' if len(nomes) > 4 else '')
    if not descricao:
        descricao = f"Compra {forma_curta}: {resumo}"

    if forma_pagamento == 'AVISTA':
        status, data_venc, data_pag = 'PAGO', hoje, hoje
    else:
        status, data_venc, data_pag = 'PREVISTO', (data_vencimento or hoje), None

    despesa = Despesa.objects.create(
        descricao=descricao,
        credor=credor or '',
        tipo=tipo_por_categoria('FORNECEDORES'),
        categoria='FORNECEDORES',
        valor=total,
        status=status,
        data_vencimento=data_venc,
        data_pagamento=data_pag,
        origem='ESTOQUE',
        forma_pagamento=forma_pagamento,
        grupo_compra=grupo,
        data_referencia=hoje,
        observacao=f"Nota com {len(itens)} item(ns). {resumo}",
    )
    return despesa


def estornar_compra(despesa):
    """Desfaz uma compra lançada pelo carrinho: tira do estoque o que entrou,
    restaura o custo médio de cada insumo, apaga as movimentações e a despesa.
    Retorna a lista de itens (na unidade de COMPRA) para recarregar o carrinho."""
    grupo = despesa.grupo_compra
    # ordem reversa: desfaz o averaging na ordem inversa da entrada
    movs = list(MovimentacaoEstoque.objects.filter(
        grupo_compra=grupo, tipo='ENTRADA').order_by('-id'))
    itens = []
    for mov in movs:
        ing = mov.ingrediente
        fator = ing.obter_fator_conversao
        ing.estoque_atual = max(Decimal('0'), (ing.estoque_atual or Decimal('0')) - mov.quantidade)
        if mov.custo_medio_antes is not None:
            ing.custo_unitario = mov.custo_medio_antes
        ing.save()
        qtd_compra = (mov.quantidade / fator) if fator else mov.quantidade
        vu_compra = (mov.valor_unitario or Decimal('0')) * fator
        itens.append({
            'ingrediente_id': ing.id,
            'nome': ing.nome,
            'unidade': ing.unidade_compra,
            'quantidade': qtd_compra,
            'valor_unitario': vu_compra,
        })

    MovimentacaoEstoque.objects.filter(grupo_compra=grupo).delete()
    meta = {
        'forma_pagamento': despesa.forma_pagamento,
        'credor': despesa.credor,
        'descricao': despesa.descricao if not despesa.descricao.startswith('Compra ') else '',
        'data_vencimento': despesa.data_vencimento.strftime('%Y-%m-%d') if despesa.data_vencimento else '',
    }
    despesa.delete()
    return list(reversed(itens)), meta
