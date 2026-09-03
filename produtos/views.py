from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q
from decimal import Decimal

from core.decorators import gestao_required
from core.utils import parse_numero_ptbr
from vendas.models import CanalVenda
from .models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal
from .forms import IngredienteForm, ProdutoForm, FichaTecnicaItemForm, PrecoCanalForm

# ==========================================
# INGREDIENTES
# ==========================================

@login_required
@gestao_required
def ingrediente_listar(request):
    busca = request.GET.get('busca', '')
    categoria = request.GET.get('categoria', '')
    
    ingredientes = Ingrediente.objects.all()
    
    if busca:
        ingredientes = ingredientes.filter(Q(nome__icontains=busca) | Q(fornecedor__icontains=busca))
    if categoria:
        ingredientes = ingredientes.filter(categoria=categoria)
        
    paginator = Paginator(ingredientes, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'busca': busca,
        'categoria_selecionada': categoria,
        'categorias': Ingrediente.CATEGORIAS
    }
    
    # Se for requisição HTMX, renderiza apenas o fragmento da tabela
    if request.headers.get('HX-Request'):
        return render(request, 'produtos/partials/ingredientes_tabela.html', context)
        
    return render(request, 'produtos/ingredientes_lista.html', context)


@login_required
@gestao_required
def ingrediente_criar(request):
    if request.method == 'POST':
        form = IngredienteForm(request.POST)
        if form.is_valid():
            ingrediente = form.save()
            messages.success(request, f"Ingrediente '{ingrediente.nome}' cadastrado com sucesso!")
            return redirect('ingrediente_listar')
    else:
        form = IngredienteForm()
        
    return render(request, 'produtos/ingrediente_form.html', {
        'form': form,
        'titulo': "Cadastrar Novo Insumo / Ingrediente"
    })


@login_required
@gestao_required
def ingrediente_editar(request, pk):
    ingrediente = get_object_or_404(Ingrediente, pk=pk)
    if request.method == 'POST':
        form = IngredienteForm(request.POST, instance=ingrediente)
        if form.is_valid():
            form.save()
            messages.success(request, f"Ingrediente '{ingrediente.nome}' atualizado com sucesso!")
            return redirect('ingrediente_listar')
    else:
        form = IngredienteForm(instance=ingrediente)
        
    return render(request, 'produtos/ingrediente_form.html', {
        'form': form,
        'titulo': f"Editar Insumo: {ingrediente.nome}"
    })


@login_required
@gestao_required
def ingrediente_excluir(request, pk):
    ingrediente = get_object_or_404(Ingrediente, pk=pk)
    if request.method == 'POST':
        nome = ingrediente.nome
        ingrediente.delete()
        messages.success(request, f"Ingrediente '{nome}' excluído com sucesso.")
        return redirect('ingrediente_listar')
    return render(request, 'produtos/ingrediente_confirm_delete.html', {'ingrediente': ingrediente})


# ==========================================
# PRODUTOS (CARDÁPIO)
# ==========================================

@login_required
@gestao_required
def produto_listar(request):
    busca = request.GET.get('busca', '')
    categoria = request.GET.get('categoria', '')
    
    produtos = Produto.objects.prefetch_related('ficha_tecnica__ingrediente', 'precos_canais__canal').all()
    
    if busca:
        produtos = produtos.filter(Q(nome__icontains=busca) | Q(descricao__icontains=busca))
    if categoria:
        produtos = produtos.filter(categoria=categoria)
        
    context = {
        'produtos': produtos,
        'busca': busca,
        'categoria_selecionada': categoria,
        'categorias': Produto.CATEGORIAS
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'produtos/partials/produtos_grid.html', context)
        
    return render(request, 'produtos/produtos_lista.html', context)


@login_required
@gestao_required
def produto_criar(request):
    if request.method == 'POST':
        form = ProdutoForm(request.POST, request.FILES)
        if form.is_valid():
            produto = form.save()
            messages.success(request, f"Produto '{produto.nome}' criado com sucesso! Agora configure sua ficha técnica.")
            return redirect('ficha_tecnica_montar', pk=produto.pk)
    else:
        form = ProdutoForm()
        
    return render(request, 'produtos/produto_form.html', {
        'form': form,
        'titulo': "Criar Novo Produto no Cardápio"
    })


@login_required
@gestao_required
def produto_editar(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    if request.method == 'POST':
        form = ProdutoForm(request.POST, request.FILES, instance=produto)
        if form.is_valid():
            form.save()
            messages.success(request, f"Produto '{produto.nome}' atualizado com sucesso!")
            return redirect('produto_listar')
    else:
        form = ProdutoForm(instance=produto)
        
    return render(request, 'produtos/produto_form.html', {
        'form': form,
        'produto': produto,
        'titulo': f"Editar Lanche: {produto.nome}"
    })


@login_required
@gestao_required
def produto_excluir(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    if request.method == 'POST':
        nome = produto.nome
        produto.delete()
        messages.success(request, f"Produto '{nome}' removido com sucesso.")
        return redirect('produto_listar')
    return render(request, 'produtos/produto_confirm_delete.html', {'produto': produto})


# ==========================================
# FICHA TÉCNICA E PREÇOS (MONTAGEM DO LANCHE)
# ==========================================

@login_required
@gestao_required
def ficha_tecnica_montar(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    
    # Adicionar INGREDIENTE à Ficha Técnica
    if request.method == 'POST' and 'add_ingrediente' in request.POST:
        ingrediente_id = request.POST.get('ingrediente')
        quantidade = request.POST.get('quantidade')
        if ingrediente_id and quantidade:
            ingrediente = get_object_or_404(Ingrediente, id=ingrediente_id)
            item, _ = FichaTecnicaItem.objects.get_or_create(
                produto=produto, ingrediente=ingrediente, produto_componente=None,
                defaults={'quantidade': parse_numero_ptbr(quantidade)},
            )
            item.quantidade = parse_numero_ptbr(quantidade)
            item.save()
            if request.headers.get('HX-Request'):
                return render(request, 'produtos/partials/ficha_tecnica_tabela.html', {'produto': produto})
        messages.success(request, "Ingrediente adicionado à ficha técnica.")
        return redirect('ficha_tecnica_montar', pk=produto.pk)

    # Adicionar PRODUTO COMPONENTE (combo) à Ficha Técnica
    if request.method == 'POST' and 'add_produto_componente' in request.POST:
        comp_id = request.POST.get('produto_componente')
        quantidade = request.POST.get('quantidade')
        if comp_id and quantidade:
            comp = get_object_or_404(Produto, id=comp_id)
            if comp.id == produto.id:
                messages.error(request, "Um produto não pode fazer parte de si mesmo.")
            else:
                item, _ = FichaTecnicaItem.objects.get_or_create(
                    produto=produto, produto_componente=comp, ingrediente=None,
                    defaults={'quantidade': parse_numero_ptbr(quantidade)},
                )
                item.quantidade = parse_numero_ptbr(quantidade)
                item.save()
                if request.headers.get('HX-Request'):
                    return render(request, 'produtos/partials/ficha_tecnica_tabela.html', {'produto': produto})
                messages.success(request, f"'{comp.nome}' adicionado ao combo.")
        return redirect('ficha_tecnica_montar', pk=produto.pk)

    # Configurar preço do canal via POST
    if request.method == 'POST' and 'update_preco' in request.POST:
        canal_id = request.POST.get('canal')
        preco = request.POST.get('preco')
        
        if canal_id and preco:
            canal = get_object_or_404(CanalVenda, id=canal_id)
            preco_dec = parse_numero_ptbr(preco)
            PrecoCanal.objects.update_or_create(
                produto=produto,
                canal=canal,
                defaults={'preco': preco_dec}
            )
            
            if request.headers.get('HX-Request'):
                precos_canais_ricos = []
                for c in CanalVenda.objects.all():
                    precos_canais_ricos.append({
                        'canal': c,
                        'preco_obj': produto.precos_canais.filter(canal=c).first(),
                    })
                return render(request, 'produtos/partials/precos_canais_tabela.html', {
                    'produto': produto,
                    'precos_canais_ricos': precos_canais_ricos
                })
                
        messages.success(request, "Preço atualizado com sucesso.")
        return redirect('ficha_tecnica_montar', pk=produto.pk)

    # Consultar ingredientes, produtos e canais cadastrados
    ingredientes_disponiveis = Ingrediente.objects.all().order_by('nome')
    produtos_disponiveis = Produto.objects.exclude(id=produto.id).order_by('categoria', 'nome')
    precos_canais_ricos = []
    for c in CanalVenda.objects.all():
        precos_canais_ricos.append({
            'canal': c,
            'preco_obj': produto.precos_canais.filter(canal=c).first(),
        })

    # Listas para o campo de busca (filtro no navegador, sem recarregar)
    ingredientes_json = [
        {'id': i.id, 'nome': f"{i.nome} ({i.get_unidade_medida_display()})"}
        for i in ingredientes_disponiveis
    ]
    produtos_json = [
        {'id': p.id, 'nome': f"{p.nome} ({p.get_categoria_display()})"}
        for p in produtos_disponiveis
    ]

    return render(request, 'produtos/ficha_tecnica.html', {
        'produto': produto,
        'ingredientes': ingredientes_disponiveis,
        'produtos_componentes': produtos_disponiveis,
        'ingredientes_json': ingredientes_json,
        'produtos_json': produtos_json,
        'precos_canais_ricos': precos_canais_ricos
    })


@login_required
@gestao_required
def ficha_tecnica_remover_ingrediente(request, produto_pk, item_pk):
    item = get_object_or_404(FichaTecnicaItem, pk=item_pk, produto_id=produto_pk)
    produto = item.produto
    item.delete()
    
    if request.headers.get('HX-Request'):
        return render(request, 'produtos/partials/ficha_tecnica_tabela.html', {'produto': produto})
        
    messages.success(request, "Ingrediente removido da receita.")
    return redirect('ficha_tecnica_montar', pk=produto.pk)


@login_required
@gestao_required
def produto_precos_parcial(request, pk):
    produto = get_object_or_404(Produto, pk=pk)
    precos_canais_ricos = []
    for c in CanalVenda.objects.all():
        precos_canais_ricos.append({
            'canal': c,
            'preco_obj': produto.precos_canais.filter(canal=c).first(),
        })
    return render(request, 'produtos/partials/precos_canais_tabela.html', {
        'produto': produto,
        'precos_canais_ricos': precos_canais_ricos
    })


