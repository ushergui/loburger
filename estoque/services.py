"""Regras de entrada de estoque: conversão de unidade, custo médio ponderado
e (para compras) a despesa única da nota."""
from decimal import Decimal

from django.utils import timezone

from produtos.models import Ingrediente
from .models import MovimentacaoEstoque

FORMA_CURTA = {'AVISTA': 'à vista', 'CARTAO': 'cartão', 'BOLETO': 'boleto', 'OUTRO': 'compra'}


def aplicar_entrada(ingrediente, qtd_compra, custo_compra_unit, tipo='ENTRADA',
                    responsavel=None, observacao=''):
    """Soma `qtd_compra` (na unidade de COMPRA) ao estoque de `ingrediente`,
    recalcula o custo médio ponderado e registra a movimentação.
    NÃO gera despesa — quem cuida disso é quem chama.
    Retorna (movimentacao, valor_total_na_unidade_de_compra)."""
    qtd_compra = Decimal(str(qtd_compra))
    custo_compra_unit = Decimal(str(custo_compra_unit or 0))
    fator = ingrediente.obter_fator_conversao

    qtd_consumo = qtd_compra * fator
    custo_consumo = (custo_compra_unit / fator) if custo_compra_unit > 0 else Decimal('0')

    if custo_consumo > 0:
        anterior = ingrediente.estoque_atual or Decimal('0')
        if anterior > 0:
            total_ant = anterior * (ingrediente.custo_unitario or Decimal('0'))
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
    total = Decimal('0.00')
    nomes = []
    for item in itens:
        ing = item['ingrediente']
        mov, valor = aplicar_entrada(
            ing, item['quantidade'], item['valor_unitario'],
            tipo='ENTRADA', responsavel=responsavel,
            observacao=f"Compra {forma_curta}.",
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
        data_referencia=hoje,
        observacao=f"Nota com {len(itens)} item(ns). {resumo}",
    )
    return despesa
