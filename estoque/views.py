from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils.formats import number_format
from decimal import Decimal

from core.decorators import gestao_required


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


