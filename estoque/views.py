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
from produtos.models import Ingrediente
from .models import MovimentacaoEstoque
from .forms import MovimentacaoEstoqueForm

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
            mov = form.save(commit=False)
            mov.responsavel = request.user
            
            # Lógica de Negócio: Atualiza fisicamente o estoque atual do ingrediente
            # com base na movimentação lançada manualmente.
            ingrediente = mov.ingrediente
            # Lógica de Negócio: Conversão automática de unidades (Compra -> Consumo)
            fator = ingrediente.obter_fator_conversao
            qtd_original = mov.quantidade
            
            # Ajusta a quantidade física na movimentação para a unidade de consumo do banco
            mov.quantidade = qtd_original * fator

            if mov.tipo in ('ENTRADA', 'ABERTURA'):
                # Valores originais digitados na unidade de compra
                custo_compra = mov.valor_unitario

                # Custo convertido para a unidade de consumo (ex: R$/kg -> R$/g)
                custo_novo = Decimal('0.0000')
                if custo_compra is not None and custo_compra > 0:
                    custo_novo = custo_compra / fator

                    # ENTRADA (compra real) gera Despesa paga. ABERTURA (carga inicial) NÃO.
                    if mov.tipo == 'ENTRADA':
                        from relatorios.models import Despesa
                        from django.utils import timezone

                        valor_total_compra = qtd_original * custo_compra
                        Despesa.objects.create(
                            descricao=f"Compra: {ingrediente.nome} ({qtd_original} {ingrediente.unidade_compra})",
                            tipo='VARIAVEL',
                            categoria='FORNECEDORES',
                            valor=valor_total_compra,
                            status='PAGO',
                            data_vencimento=timezone.localdate(),
                            data_pagamento=timezone.localdate(),
                            origem='ESTOQUE',
                            data_referencia=timezone.localdate(),
                            observacao=f"Gerada automaticamente pela entrada no estoque. {mov.observacao or ''}".strip(),
                        )

                mov.valor_unitario = custo_novo

                qtd_anterior = ingrediente.estoque_atual
                custo_anterior = ingrediente.custo_unitario
                qtd_nova = mov.quantidade

                if custo_novo > 0:
                    if qtd_anterior > 0:
                        valor_total_anterior = qtd_anterior * custo_anterior
                        valor_total_novo = qtd_nova * custo_novo
                        novo_custo_medio = (valor_total_anterior + valor_total_novo) / (qtd_anterior + qtd_nova)
                    else:
                        novo_custo_medio = custo_novo
                    ingrediente.custo_unitario = novo_custo_medio

                ingrediente.estoque_atual += qtd_nova
                rotulo = "Carga inicial" if mov.tipo == 'ABERTURA' else "Entrada"
                custo_kg = _n(ingrediente.custo_unitario * fator, 2)
                messages.success(
                    request,
                    f"{rotulo}: +{_n(qtd_original)} {ingrediente.unidade_compra} "
                    f"em '{ingrediente.nome}'. "
                    f"Custo médio: R$ {custo_kg}/{ingrediente.unidade_compra}."
                    + ("" if mov.tipo == 'ENTRADA' else " Não gerou despesa (abertura).")
                )
            else:
                ingrediente.estoque_atual -= mov.quantidade
                motivo = {
                    'SAIDA_PERDA': 'perda / descarte',
                    'SAIDA_AUTOCONSUMO': 'autoconsumo',
                    'AJUSTE': 'ajuste de inventário',
                }.get(mov.tipo, 'ajuste')
                messages.success(
                    request,
                    f"Baixa por {motivo}: -{_n(qtd_original)} {ingrediente.unidade_compra} "
                    f"em '{ingrediente.nome}'. "
                    "Não gera despesa — o insumo já foi pago na compra."
                )
            
            # Salva a atualização física do insumo e a movimentação no banco
            ingrediente.save()
            mov.save()

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
            form = MovimentacaoEstoqueForm(initial={
                'ingrediente': ingrediente_selecionado,
                'tipo': 'ENTRADA'
            })
        else:
            form = MovimentacaoEstoqueForm()

    return render(request, 'estoque/ajuste_form.html', {
        'form': form,
        'titulo': "Lançar Movimentação de Estoque Manual",
        'ingrediente_selecionado': ingrediente_selecionado
    })


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


