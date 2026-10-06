import re

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils.formats import number_format
from decimal import Decimal

from core.decorators import gestao_required
from core.utils import parse_numero_ptbr


def _n(valor, casas=3):
    """Número no formato brasileiro (1.234,560)."""
    try:
        q = Decimal(valor).quantize(Decimal('1.' + '0' * casas)).normalize()
    except Exception:
        q = Decimal(valor or 0)
    return number_format(q, use_l10n=True, force_grouping=True)


def _money(valor):
    """Valor em reais no formato brasileiro, sempre 2 casas (1.234,50)."""
    try:
        q = Decimal(valor).quantize(Decimal('0.01'))
    except Exception:
        q = Decimal('0.00')
    return number_format(q, decimal_pos=2, use_l10n=True, force_grouping=True)


from produtos.models import Ingrediente  # noqa: E402
from .models import MovimentacaoEstoque  # noqa: E402
from .forms import MovimentacaoEstoqueForm  # noqa: E402
from . import services  # noqa: E402

@login_required
def estoque_resumo(request):
    busca = request.GET.get('busca', '')
    status_filtro = request.GET.get('status', '')
    
    ingredientes = Ingrediente.objects.all()
    
    if busca:
        ingredientes = ingredientes.filter(Q(nome__icontains=busca) | Q(categoria__icontains=busca))
        
    # Filtro customizado baseado no status reativo de estoque
    if status_filtro:
        lista_filtrada = []
        for ing in ingredientes:
            if ing.status_estoque == status_filtro:
                lista_filtrada.append(ing.id)
        ingredientes = ingredientes.filter(id__in=lista_filtrada)
        
    # Alertas proativos de estoque baixo no dashboard/menu
    from django.db.models import F
    alertas_baixo = Ingrediente.objects.filter(Q(estoque_atual__lt=F('estoque_minimo')) | Q(estoque_atual__lte=0))
    
    context = {
        'ingredientes': ingredientes,
        'busca': busca,
        'status_selecionado': status_filtro,
        'alertas_count': alertas_baixo.count(),
        'alertas': alertas_baixo[:5] # Apenas os primeiros 5 alertas
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'estoque/partials/estoque_tabela.html', context)
        
    return render(request, 'estoque/resumo.html', context)


@login_required
@gestao_required
def estoque_historico(request):
    busca = request.GET.get('busca', '')
    tipo_filtro = request.GET.get('tipo', '')
    
    movimentacoes = MovimentacaoEstoque.objects.select_related('ingrediente', 'responsavel').all()
    
    if busca:
        movimentacoes = movimentacoes.filter(Q(ingrediente__nome__icontains=busca) | Q(observacao__icontains=busca))
    if tipo_filtro:
        movimentacoes = movimentacoes.filter(tipo=tipo_filtro)
        
    paginator = Paginator(movimentacoes, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'busca': busca,
        'tipo_selecionado': tipo_filtro,
        'tipos': MovimentacaoEstoque.TIPOS_MOVIMENTACAO
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'estoque/partials/historico_tabela.html', context)
        
    return render(request, 'estoque/historico.html', context)


@login_required
def estoque_ajustar(request):
    if request.method == 'POST':
        form = MovimentacaoEstoqueForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            ingrediente = cd['ingrediente']
            tipo = cd['tipo']
            fator = ingrediente.obter_fator_conversao
            qtd_original = cd['quantidade']

            if tipo == 'ABERTURA':
                mov, _valor = services.aplicar_entrada(
                    ingrediente, qtd_original, cd.get('valor_unitario') or 0,
                    tipo='ABERTURA', responsavel=request.user,
                    observacao=cd.get('observacao') or '',
                )
                custo_un = _n(ingrediente.custo_unitario * fator, 2)
                messages.success(
                    request,
                    f"Carga inicial: +{_n(qtd_original)} {ingrediente.unidade_compra} "
                    f"em '{ingrediente.nome}'. Custo: R$ {custo_un}/{ingrediente.unidade_compra}. "
                    "Não gerou despesa (abertura)."
                )
            else:
                mov = form.save(commit=False)
                mov.responsavel = request.user
                mov.quantidade = qtd_original * fator
                ingrediente.estoque_atual = (ingrediente.estoque_atual or Decimal('0')) - mov.quantidade
                ingrediente.save()
                mov.save()
                motivo = {
                    'SAIDA_PERDA': 'perda / descarte',
                    'SAIDA_AUTOCONSUMO': 'autoconsumo',
                    'AJUSTE': 'ajuste de inventário',
                }.get(tipo, 'ajuste')
                messages.success(
                    request,
                    f"Baixa por {motivo}: -{_n(qtd_original)} {ingrediente.unidade_compra} "
                    f"em '{ingrediente.nome}'. Não gera despesa — o insumo já foi pago na compra."
                )

            return redirect('estoque_resumo')
        else:
            # POST inválido: mantém o insumo escolhido visível no formulário
            messages.error(request, "Não foi possível salvar a movimentação. Confira os campos destacados abaixo.")
            ingrediente_selecionado = Ingrediente.objects.filter(id=request.POST.get('ingrediente') or 0).first()
    else:
        ingrediente_selecionado = None
        ingrediente_id = request.GET.get('ingrediente_id')
        if ingrediente_id:
            ingrediente_selecionado = get_object_or_404(Ingrediente, id=ingrediente_id)
            form = MovimentacaoEstoqueForm(initial={'ingrediente': ingrediente_selecionado})
        else:
            form = MovimentacaoEstoqueForm()

    return render(request, 'estoque/ajuste_form.html', {
        'form': form,
        'titulo': "Ajuste de Estoque (perda, autoconsumo, carga inicial)",
        'ingrediente_selecionado': ingrediente_selecionado
    })


@login_required
def estoque_compra(request):
    """Carrinho de compra: adiciona vários insumos de uma nota e no fim escolhe
    a forma de pagamento (à vista = despesa paga; cartão/boleto = despesa prevista)."""
    from relatorios.models import Despesa

    cart = request.session.get('compra_cart', [])

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'add_item':
            from core.utils import parse_numero_ptbr
            ing_id = request.POST.get('ingrediente')
            qtd = parse_numero_ptbr(request.POST.get('quantidade'))
            valor = parse_numero_ptbr(request.POST.get('valor_unitario'))
            ing = Ingrediente.objects.filter(id=ing_id).first()
            if ing and qtd and qtd > 0 and valor is not None and valor >= 0:
                sub = (qtd * valor).quantize(Decimal('0.01'))
                cart.append({
                    'ingrediente_id': ing.id,
                    'nome': ing.nome,
                    'unidade': ing.unidade_compra,
                    'quantidade': str(qtd),
                    'valor_unitario': str(valor),
                    'subtotal': str(sub),
                    'q_disp': _n(qtd),
                    'vu_disp': _money(valor),
                    'sub_disp': _money(sub),
                })
                request.session['compra_cart'] = cart
                request.session.modified = True
            return _render_carrinho(request, cart)

        if acao == 'remove_item':
            try:
                idx = int(request.POST.get('idx'))
                cart.pop(idx)
            except (ValueError, IndexError):
                pass
            request.session['compra_cart'] = cart
            request.session.modified = True
            return _render_carrinho(request, cart)

        if acao == 'limpar':
            request.session['compra_cart'] = []
            request.session.modified = True
            return _render_carrinho(request, [])

        if acao == 'finalizar':
            if not cart:
                messages.error(request, "O carrinho está vazio.")
                return redirect('estoque_compra')
            forma = request.POST.get('forma_pagamento', 'AVISTA')
            credor = (request.POST.get('credor') or '').strip()
            descricao = (request.POST.get('descricao') or '').strip()
            data_venc = None
            if forma != 'AVISTA':
                from datetime import datetime as _dt
                try:
                    data_venc = _dt.strptime(request.POST.get('data_vencimento', ''), '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Informe a data de vencimento para pagamento em cartão ou boleto.")
                    return redirect('estoque_compra')

            itens = []
            for linha in cart:
                ing = Ingrediente.objects.filter(id=linha['ingrediente_id']).first()
                if ing:
                    itens.append({
                        'ingrediente': ing,
                        'quantidade': Decimal(linha['quantidade']),
                        'valor_unitario': Decimal(linha['valor_unitario']),
                    })
            despesa = services.registrar_compra(
                itens, forma, credor, data_venc, descricao, responsavel=request.user)

            request.session['compra_cart'] = []
            request.session.pop('compra_meta', None)
            request.session.modified = True

            if despesa.status == 'PAGO':
                messages.success(
                    request,
                    f"Compra registrada: {len(itens)} insumo(s), total R$ {_money(despesa.valor)}. "
                    "Despesa lançada como PAGA hoje."
                )
            else:
                messages.success(
                    request,
                    f"Compra registrada: {len(itens)} insumo(s), total R$ {_money(despesa.valor)}. "
                    f"Despesa PREVISTA ({despesa.get_forma_pagamento_display()}) para "
                    f"{despesa.data_vencimento.strftime('%d/%m/%Y')} — pague em Contas a Pagar."
                )
            return redirect('estoque_resumo')

    total = sum(Decimal(l['subtotal']) for l in cart) if cart else Decimal('0.00')
    ingredientes_json = [
        {'id': i.id, 'nome': f"{i.nome} ({i.get_unidade_compra_display()})"}
        for i in Ingrediente.objects.all().order_by('nome')
    ]
    return render(request, 'estoque/compra.html', {
        'cart': cart,
        'total': total,
        'ingredientes_json': ingredientes_json,
        'formas': Despesa.FORMA_PAGAMENTO_CHOICES,
        'meta': request.session.get('compra_meta', {}),
    })


@login_required
@gestao_required
def estoque_compra_editar(request, despesa_id):
    """Reabre no carrinho uma compra lançada pelo carrinho, para o usuário
    corrigir (quantidade errada de um insumo, etc.)."""
    from relatorios.models import Despesa
    despesa = get_object_or_404(Despesa, id=despesa_id, origem='ESTOQUE')

    if not despesa.grupo_compra:
        messages.info(request, "Essa despesa não veio do carrinho — edite os campos direto.")
        return redirect('despesa_editar', id=despesa.id)

    movs = MovimentacaoEstoque.objects.filter(grupo_compra=despesa.grupo_compra, tipo='ENTRADA')

    if request.method == 'POST':
        itens, meta = services.estornar_compra(despesa)
        cart = []
        for it in itens:
            sub = (it['quantidade'] * it['valor_unitario']).quantize(Decimal('0.01'))
            cart.append({
                'ingrediente_id': it['ingrediente_id'],
                'nome': it['nome'],
                'unidade': it['unidade'],
                'quantidade': str(it['quantidade']),
                'valor_unitario': str(it['valor_unitario']),
                'subtotal': str(sub),
                'q_disp': _n(it['quantidade']),
                'vu_disp': _money(it['valor_unitario']),
                'sub_disp': _money(sub),
            })
        request.session['compra_cart'] = cart
        request.session['compra_meta'] = meta
        request.session.modified = True
        messages.info(
            request,
            f"Compra reaberta no carrinho ({len(cart)} item(ns)). O lançamento anterior "
            "(estoque e despesa) foi desfeito — ajuste o que precisar e finalize de novo."
        )
        return redirect('estoque_compra')

    linhas = []
    for m in movs:
        fator = m.ingrediente.obter_fator_conversao
        linhas.append({
            'nome': m.ingrediente.nome,
            'qtd': _n(m.quantidade / fator if fator else m.quantidade),
            'unidade': m.ingrediente.unidade_compra,
        })
    return render(request, 'estoque/compra_editar_confirm.html', {
        'despesa': despesa,
        'linhas': linhas,
    })


def _render_carrinho(request, cart):
    total = sum(Decimal(l['subtotal']) for l in cart) if cart else Decimal('0.00')
    return render(request, 'estoque/partials/compra_carrinho.html', {'cart': cart, 'total': total})


@login_required
def estoque_buscar_ingredientes(request):
    # Lógica de Negócio: Busca assíncrona (AJAX) para seleção rápida de insumos
    q = request.GET.get('q', '')
    if q:
        ingredientes = Ingrediente.objects.filter(nome__icontains=q)[:10]
    else:
        ingredientes = Ingrediente.objects.all()[:10]
        
    return render(request, 'estoque/partials/ingredientes_busca_resultados.html', {
        'ingredientes': ingredientes
    })




# ==========================================
# CONTAGEM DE ESTOQUE (acertar para a quantidade real)
# ==========================================

def _plain(valor, casas):
    """Número para dentro de um campo de digitação: vírgula decimal e SEM separador de
    milhar (1000 e não 1.000 — o ponto único seria lido como decimal)."""
    q = Decimal(valor).quantize(Decimal('1.' + '0' * casas)).normalize()
    return format(q, 'f').replace('.', ',')


_MILHAR = re.compile(r'^[1-9]\d{0,2}(\.\d{3})+$')


def _parse_qtd_contagem(texto):
    """Quantidade digitada: vírgula = decimal; "1.000" (ponto com grupos de 3 dígitos,
    sem vírgula) = mil. Para casas decimais, use a vírgula (2,5)."""
    t = (texto or '').replace(' ', '')
    if _MILHAR.match(t):
        t = t.replace('.', '')
    return parse_numero_ptbr(t)


def _unidade_contagem(ing):
    """Unidade em que o estoque é mostrado/digitado (a mesma de estoque_display)."""
    return ing.unidade_compra if ing.obter_fator_conversao > 1 else ing.unidade_medida


@login_required
@gestao_required
def estoque_contagem(request):
    """Planilha de contagem: a pessoa digita o que TEM de verdade na prateleira
    (e, se quiser, corrige o custo) e o sistema acerta a diferença sozinho.

    Regras de negócio (diferente do 'Ajuste', que só SUBTRAI):
    - quantidade maior que a do sistema -> entra como Carga Inicial (ABERTURA), no
      custo atual do insumo; NÃO gera despesa e NÃO mexe no caixa;
    - quantidade menor -> baixa por Ajuste de Inventário; também não gera despesa;
    - custo corrigido -> vira o novo custo do insumo (por unidade de compra/consumo).
    Tudo em uma transação: se alguma linha estiver inválida, nada é gravado."""
    from django.db import transaction

    ingredientes = list(Ingrediente.objects.all().order_by('nome'))
    linhas = []
    erros = []
    postado = request.method == 'POST'

    for ing in ingredientes:
        fator = ing.obter_fator_conversao
        qtd_atual = ((ing.estoque_atual or Decimal('0')) / fator).quantize(Decimal('0.001'))
        custo_atual = ((ing.custo_unitario or Decimal('0')) * fator).quantize(Decimal('0.0001'))
        linha = {
            'ing': ing,
            'unidade': _unidade_contagem(ing),
            'qtd_atual': qtd_atual,
            'custo_atual': custo_atual,
            'qtd_txt': _plain(qtd_atual, 3),
            'custo_txt': _plain(custo_atual, 4),
            # o que o sistema tem hoje (não muda mesmo se a tela voltar com erro)
            'sistema_qtd_txt': _plain(qtd_atual, 3),
            'sistema_custo_txt': _plain(custo_atual, 4),
            'qtd_bonita': _n(qtd_atual, 3),
            # unidades de compra/consumo que não combinam: a conversão seria errada, então a linha fica travada
            'bloqueado': not ing.unidades_coerentes,
            'erro': '',
        }
        if postado and not linha['bloqueado']:
            linha['qtd_txt'] = (request.POST.get(f'qtd_{ing.id}') or '').strip()
            linha['custo_txt'] = (request.POST.get(f'custo_{ing.id}') or '').strip()
            linha['nova_qtd'] = None
            linha['novo_custo'] = None
            if linha['qtd_txt']:
                v = _parse_qtd_contagem(linha['qtd_txt'])
                if v is None or v < 0:
                    linha['erro'] = 'Quantidade inválida (use número, sem negativo).'
                else:
                    linha['nova_qtd'] = v.quantize(Decimal('0.001'))
            if linha['custo_txt'] and not linha['erro']:
                v = parse_numero_ptbr(linha['custo_txt'])
                if v is None or v < 0:
                    linha['erro'] = 'Custo inválido.'
                else:
                    linha['novo_custo'] = v.quantize(Decimal('0.0001'))
            if linha['erro']:
                erros.append(f"{ing.nome}: {linha['erro']}")
        linhas.append(linha)

    if postado and not erros:
        n_qtd = n_custo = 0
        with transaction.atomic():
            for l in linhas:
                if l['bloqueado']:
                    continue
                ing = l['ing']
                fator = ing.obter_fator_conversao
                # 1) custo primeiro, para a carga entrar já no custo corrigido
                nc = l.get('novo_custo')
                if nc is not None and nc != l['custo_atual']:
                    ing.custo_unitario = (nc / fator)
                    ing.save()
                    n_custo += 1
                # 2) quantidade: acerta a diferença
                nq = l.get('nova_qtd')
                if nq is not None and nq != l['qtd_atual']:
                    nova_base = (nq * fator).quantize(Decimal('0.01'))
                    atual_base = ing.estoque_atual or Decimal('0')
                    diff = nova_base - atual_base
                    if diff == 0:
                        continue
                    if diff > 0:
                        MovimentacaoEstoque.objects.create(
                            ingrediente=ing, quantidade=diff, tipo='ABERTURA',
                            valor_unitario=ing.custo_unitario, responsavel=request.user,
                            observacao='Contagem de estoque (acerto para mais).',
                            custo_medio_antes=ing.custo_unitario,
                        )
                    else:
                        MovimentacaoEstoque.objects.create(
                            ingrediente=ing, quantidade=-diff, tipo='AJUSTE',
                            responsavel=request.user,
                            observacao='Contagem de estoque (acerto para menos).',
                        )
                    ing.estoque_atual = nova_base
                    ing.save()
                    n_qtd += 1
        if n_qtd or n_custo:
            messages.success(
                request,
                f"Contagem salva: {n_qtd} quantidade(s) e {n_custo} custo(s) acertados. "
                "Nenhuma despesa foi criada e o caixa não mudou."
            )
        else:
            messages.info(request, "Nada mudou: as quantidades e custos digitados são iguais aos do sistema.")
        return redirect('estoque_contagem')
    if postado and erros:
        messages.error(request, "Nada foi salvo. Corrija: " + " | ".join(erros[:5]))

    return render(request, 'estoque/contagem.html', {'linhas': linhas})
