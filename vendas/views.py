from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q, Sum, Case, When, Value, IntegerField
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, date

from core.decorators import gestao_required
from produtos.models import Produto, PrecoCanal, Ingrediente
from .models import CanalVenda, TaxaFormaPagamento, FormaPagamento, Pedido, PedidoItem, FechamentoDiarioInfo
from .forms import CanalVendaForm, TaxaFormaPagamentoFormSet, FormaPagamentoForm

# ==========================================
# CANAIS DE VENDA (GESTÃO)
# ==========================================

@login_required
@gestao_required
def canal_listar(request):
    canais = CanalVenda.objects.all()
    return render(request, 'vendas/canal_lista.html', {'canais': canais})


@login_required
@gestao_required
def canal_criar(request):
    if request.method == 'POST':
        form = CanalVendaForm(request.POST)
        if form.is_valid():
            canal = form.save()
            formset = TaxaFormaPagamentoFormSet(request.POST, instance=canal)
            if formset.is_valid():
                formset.save()
                messages.success(request, f"Canal de venda '{canal.nome}' cadastrado!")
                return redirect('canal_listar')
            else:
                # Se o formset for inválido, apaga o canal pra não ficar órfão (ou apenas exibe o erro)
                canal.delete()
        else:
            formset = TaxaFormaPagamentoFormSet(request.POST)
    else:
        form = CanalVendaForm()
        formset = TaxaFormaPagamentoFormSet()
    
    return render(request, 'vendas/canal_form.html', {
        'form': form, 
        'formset': formset,
        'titulo': "Cadastrar Canal de Venda"
    })


@login_required
@gestao_required
def canal_editar(request, pk):
    canal = get_object_or_404(CanalVenda, pk=pk)
    if request.method == 'POST':
        form = CanalVendaForm(request.POST, instance=canal)
        formset = TaxaFormaPagamentoFormSet(request.POST, instance=canal)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Canal '{canal.nome}' atualizado!")
            return redirect('canal_listar')
    else:
        form = CanalVendaForm(instance=canal)
        formset = TaxaFormaPagamentoFormSet(instance=canal)
        
    return render(request, 'vendas/canal_form.html', {
        'form': form, 
        'formset': formset,
        'titulo': f"Editar Canal: {canal.nome}"
    })


@login_required
@gestao_required
def canal_excluir(request, pk):
    canal = get_object_or_404(CanalVenda, pk=pk)
    if request.method == 'POST':
        nome = canal.nome
        canal.delete()
        messages.success(request, f"Canal '{nome}' excluído.")
        return redirect('canal_listar')
    return render(request, 'vendas/canal_confirm_delete.html', {'canal': canal})


# ==========================================
# FORMAS DE PAGAMENTO (GESTÃO)
# ==========================================

@login_required
@gestao_required
def forma_pagamento_listar(request):
    formas = FormaPagamento.objects.all()
    return render(request, 'vendas/forma_pagamento_lista.html', {'formas': formas})

@login_required
@gestao_required
def forma_pagamento_criar(request):
    if request.method == 'POST':
        form = FormaPagamentoForm(request.POST)
        if form.is_valid():
            fp = form.save()
            messages.success(request, f"Forma de Pagamento '{fp.nome}' cadastrada!")
            return redirect('forma_pagamento_listar')
    else:
        form = FormaPagamentoForm()
    return render(request, 'vendas/forma_pagamento_form.html', {'form': form, 'titulo': "Cadastrar Forma de Pagamento"})

@login_required
@gestao_required
def forma_pagamento_editar(request, pk):
    fp = get_object_or_404(FormaPagamento, pk=pk)
    if request.method == 'POST':
        form = FormaPagamentoForm(request.POST, instance=fp)
        if form.is_valid():
            form.save()
            messages.success(request, f"Forma de Pagamento '{fp.nome}' atualizada!")
            return redirect('forma_pagamento_listar')
    else:
        form = FormaPagamentoForm(instance=fp)
    return render(request, 'vendas/forma_pagamento_form.html', {'form': form, 'titulo': f"Editar Forma de Pagamento: {fp.nome}"})

@login_required
@gestao_required
def forma_pagamento_excluir(request, pk):
    fp = get_object_or_404(FormaPagamento, pk=pk)
    if request.method == 'POST':
        nome = fp.nome
        try:
            fp.delete()
            messages.success(request, f"Forma de Pagamento '{nome}' excluída.")
        except Exception as e:
            messages.error(request, "Não é possível excluir esta forma de pagamento pois ela já foi utilizada em vendas ou canais.")
        return redirect('forma_pagamento_listar')
    return render(request, 'vendas/forma_pagamento_confirm_delete.html', {'forma': fp})


# ==========================================
# LANÇAMENTO DE PEDIDO (CAIXA / BALCÃO)
# ==========================================

@login_required
def pedido_criar(request):
    # Inicializa ou recupera o estado do pedido temporário na sessão
    if 'carrinho' not in request.session or request.GET.get('novo') == '1':
        default_canal = CanalVenda.objects.first()
        request.session['carrinho'] = {
            'canal_id': default_canal.id if default_canal else None,
            'cliente_nome': '',
            'itens': {} # Formato: { "produto_id": quantidade }
        }
        request.session.modified = True

    # Trata adição, remoção e alterações via POST/HTMX
    if request.method == 'POST':
        carrinho = request.session.get('carrinho', {})
        
        # 1. Alterar o Canal de Venda
        if 'atualizar_canal' in request.POST:
            canal_id = request.POST.get('canal')
            if canal_id:
                carrinho['canal_id'] = int(canal_id)
                request.session['carrinho'] = carrinho
                request.session.modified = True
                
        # 2. Adicionar / Ajustar Item
        elif 'adicionar_item' in request.POST:
            prod_id = request.POST.get('produto_id')
            if prod_id:
                itens = carrinho.get('itens', {})
                # Soma mais 1 se já existir, senão define como 1
                itens[str(prod_id)] = itens.get(str(prod_id), 0) + 1
                carrinho['itens'] = itens
                request.session['carrinho'] = carrinho
                request.session.modified = True
                
        # 3. Remover Item
        elif 'remover_item' in request.POST:
            prod_id = request.POST.get('produto_id')
            if prod_id:
                itens = carrinho.get('itens', {})
                if str(prod_id) in itens:
                    del itens[str(prod_id)]
                carrinho['itens'] = itens
                request.session['carrinho'] = carrinho
                request.session.modified = True
                
        # 4. Alterar Quantidade Direta
        elif 'alterar_qtd' in request.POST:
            prod_id = request.POST.get('produto_id')
            qtd = request.POST.get('quantidade')
            if prod_id and qtd:
                itens = carrinho.get('itens', {})
                if int(qtd) > 0:
                    itens[str(prod_id)] = int(qtd)
                else:
                    if str(prod_id) in itens:
                        del itens[str(prod_id)]
                carrinho['itens'] = itens
                request.session['carrinho'] = carrinho
                request.session.modified = True

        # 5. Salvar Pedido no Banco (Finalizar Venda)
        elif 'finalizar_pedido' in request.POST:
            cliente_nome = request.POST.get('cliente_nome', '')
            canal_id = carrinho.get('canal_id')
            itens = carrinho.get('itens', {})
            
            if not canal_id:
                messages.error(request, "Selecione um canal de venda.")
                return redirect('pedido_criar')
            if not itens:
                messages.error(request, "Adicione ao menos um lanche ao pedido.")
                return redirect('pedido_criar')
                
            canal = get_object_or_404(CanalVenda, id=canal_id)
            
            # Validação proativa de estoque insuficiente (Apenas avisa, não bloqueia)
            alerta_estoque = False
            mensagens_alerta = []
            
            # Cria o objeto de pedido provisório
            pedido = Pedido(cliente_nome=cliente_nome, canal=canal, status='RECEBIDO')
            pedido.save()
            
            for prod_id, qtd in itens.items():
                produto = get_object_or_404(Produto, id=int(prod_id))
                # Carrega o preço no canal
                preco_canal = PrecoCanal.objects.filter(produto=produto, canal=canal).first()
                preco_venda = preco_canal.preco if preco_canal else Decimal('0.00')
                
                # Valida os ingredientes da ficha técnica
                for ft in produto.ficha_tecnica.all():
                    necessario = ft.quantidade * Decimal(qtd)
                    if ft.ingrediente.estoque_atual < necessario:
                        alerta_estoque = True
                        mensagens_alerta.append(f"{ft.ingrediente.nome} insuficiente (Necessário: {necessario}{ft.ingrediente.unidade_medida}, Disponível: {ft.ingrediente.estoque_atual}{ft.ingrediente.unidade_medida})")

                # Cria o Item do Pedido
                PedidoItem.objects.create(
                    pedido=pedido,
                    produto=produto,
                    quantidade=qtd,
                    preco_unitario=preco_venda
                )
            
            # Roda recálculo de taxas, comissões e lucro líquido
            pedido.recalcular_valores_financeiros(save=True)
            # O sinal 'post_save' vai processar a baixa de estoque automaticamente!
            
            if alerta_estoque:
                # Caso a opção A seja ativa: exibe toast de aviso proativo, mas não bloqueia a venda
                alerta_msg = "⚠️ Pedido finalizado com avisos de estoque insuficiente: " + ", ".join(mensagens_alerta)
                messages.warning(request, alerta_msg)
            else:
                messages.success(request, f"Pedido #{pedido.id} lançado com sucesso e estoque baixado!")
                
            # Limpa carrinho na sessão
            del request.session['carrinho']
            request.session.modified = True
            return redirect('pedido_listar')

        # Se for requisição HTMX parcial (atualiza o carrinho lateral na tela)
        if request.headers.get('HX-Request'):
            carrinho_temp = request.session.get('carrinho', {})
            canal_id = carrinho_temp.get('canal_id')
            canal = CanalVenda.objects.filter(id=canal_id).first() if canal_id else None
            prod_carrinho = self_obter_produtos_carrinho(carrinho_temp)
            totais = self_obter_totais_carrinho(prod_carrinho, canal)
            return render(request, 'vendas/partials/carrinho_painel.html', {
                'carrinho': carrinho_temp,
                'produtos_carrinho': prod_carrinho,
                'totais': totais,
                'canais': CanalVenda.objects.all()
            })

    # Renderização Inicial (GET)
    carrinho_sessao = request.session.get('carrinho', {})
    canal_id = carrinho_sessao.get('canal_id')
    canal = CanalVenda.objects.filter(id=canal_id).first() if canal_id else None
    produtos_carrinho = self_obter_produtos_carrinho(carrinho_sessao)
    totais = self_obter_totais_carrinho(produtos_carrinho, canal)
    
    # Produtos disponíveis ativos do cardápio
    busca_lanche = request.GET.get('busca_lanche', '')
    produtos = Produto.objects.filter(status=True)
    if busca_lanche:
        produtos = produtos.filter(nome__icontains=busca_lanche)
        
    context = {
        'produtos': produtos,
        'canais': CanalVenda.objects.all(),
        'carrinho': carrinho_sessao,
        'produtos_carrinho': produtos_carrinho,
        'totais': totais,
        'busca_lanche': busca_lanche
    }
    
    if request.headers.get('HX-Request') and 'busca_lanche' in request.GET:
        return render(request, 'vendas/partials/produtos_vitrine.html', context)
        
    return render(request, 'vendas/pedido_form.html', context)


def self_obter_produtos_carrinho(carrinho):
    # Função auxiliar para enriquecer os dados do carrinho temporário da sessão
    if not carrinho or not carrinho.get('itens'):
        return []
        
    canal_id = carrinho.get('canal_id')
    canal = CanalVenda.objects.filter(id=canal_id).first() if canal_id else None
    
    lista = []
    for prod_id, qtd in carrinho.get('itens').items():
        produto = Produto.objects.filter(id=int(prod_id)).first()
        if produto:
            preco_canal = PrecoCanal.objects.filter(produto=produto, canal=canal).first() if canal else None
            preco = preco_canal.preco if preco_canal else Decimal('0.00')
            subtotal = preco * Decimal(qtd)
            lista.append({
                'produto': produto,
                'quantidade': qtd,
                'preco': preco,
                'subtotal': subtotal
            })
    return lista


def self_obter_totais_carrinho(produtos_carrinho, canal):
    # Lógica de Negócio: Consolida os totais financeiros do carrinho temporário
    # para exibir a margem de contribuição estimada e o faturamento.
    bruto = Decimal('0.00')
    custo = Decimal('0.00')
    for item in produtos_carrinho:
        bruto += item['subtotal']
        custo += item['produto'].custo_total * Decimal(item['quantidade'])
    
    taxas = Decimal('0.00')
    if canal and bruto > 0:
        taxas = bruto * canal.taxa_comissao + canal.taxa_fixa
        
    lucro = bruto - taxas - custo
    margem = ((lucro / bruto) * 100) if bruto > 0 else Decimal('0.00')
    
    return {
        'bruto': bruto.quantize(Decimal('0.01')),
        'custo': custo.quantize(Decimal('0.01')),
        'taxas': taxas.quantize(Decimal('0.01')),
        'lucro': lucro.quantize(Decimal('0.01')),
        'margem': margem.quantize(Decimal('0.01'))
    }



# ==========================================
# PAINEL KANBAN / LISTA DE PEDIDOS
# ==========================================

@login_required
def pedido_listar(request):
    status_filtro = request.GET.get('status', '')
    busca = request.GET.get('busca', '')
    
    pedidos = Pedido.objects.select_related('canal').prefetch_related('itens__produto').all()
    
    if status_filtro:
        pedidos = pedidos.filter(status=status_filtro)
    if busca:
        pedidos = pedidos.filter(Q(id__icontains=busca) | Q(cliente_nome__icontains=busca))
        
    paginator = Paginator(pedidos, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_selecionado': status_filtro,
        'busca': busca,
        'status_choices': Pedido.STATUS_CHOICES
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'vendas/partials/pedidos_lista_cards.html', context)
        
    return render(request, 'vendas/pedidos_painel.html', context)


@login_required
def pedido_atualizar_status(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    novo_status = request.POST.get('status')
    
    if novo_status in dict(Pedido.STATUS_CHOICES):
        # Permissões: Operador não pode cancelar pedidos concluídos (regra do negócio opcional)
        pedido.status = novo_status
        pedido.save() # Dispara sinal post_save para ajuste de estoque automática!
        
        # Se for HTMX, retorna apenas o bloco daquele pedido atualizado
        if request.headers.get('HX-Request'):
            return render(request, 'vendas/partials/pedido_card_item.html', {'pedido': pedido})
            
        messages.success(request, f"Status do Pedido #{pedido.id} atualizado para {pedido.get_status_display()}!")
        
    return redirect('pedido_listar')


# ==========================================
# FECHAMENTO DIÁRIO DE VENDAS EM LOTE
# ==========================================

@login_required
def fechamento_diario(request):
    data_str = request.GET.get('data') or request.POST.get('data') or timezone.localdate().strftime('%Y-%m-%d')
    try:
        data_fechamento = datetime.strptime(data_str, '%Y-%m-%d').date()
    except ValueError:
        data_fechamento = timezone.localdate()
        data_str = data_fechamento.strftime('%Y-%m-%d')

    busca = request.GET.get('busca', '').strip()
    categoria_filtro = request.GET.get('categoria', '').strip()

    canais = CanalVenda.objects.all().prefetch_related('taxas_pagamento')
    produtos = Produto.objects.filter(status=True).annotate(
        ordem_categoria=Case(
            When(categoria='BURGER', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by('ordem_categoria', 'nome').prefetch_related('precos_canais', 'ficha_tecnica')

    if busca:
        produtos = produtos.filter(Q(nome__icontains=busca) | Q(descricao__icontains=busca))

    if categoria_filtro:
        produtos = produtos.filter(categoria=categoria_filtro)

    # Mapeamento de preços por produto e canal {produto_id: {canal_id: preco}}
    precos_matriz = {}
    for p in produtos:
        precos_matriz[p.id] = {}
        for pc in p.precos_canais.all():
            precos_matriz[p.id][pc.canal_id] = pc.preco

    # Buscar pedidos existentes da data
    pedidos_dia = Pedido.objects.filter(
        data_criacao__date=data_fechamento,
        status='CONCLUIDO'
    ).prefetch_related('itens', 'canal')

    # Mapeamento de vendas gravadas {produto_id: {f"{canal_id}_{forma_pagamento}": qtd}}
    vendas_gravadas = {}
    total_entregas_dia = 0
    desconto_dia = Decimal('0.00')

    for ped in pedidos_dia:
        if ped.cliente_nome and 'Fechamento Diário' in ped.cliente_nome:
            if ped.desconto > 0:
                desconto_dia = ped.desconto
        for item in ped.itens.all():
            if item.produto_id not in vendas_gravadas:
                vendas_gravadas[item.produto_id] = {}
            if ped.forma_pagamento:
                chave = f"{ped.canal_id}_{ped.forma_pagamento.id}"
                vendas_gravadas[item.produto_id][chave] = vendas_gravadas[item.produto_id].get(chave, 0) + item.quantidade
            total_entregas_dia += item.quantidade

    info_dia = FechamentoDiarioInfo.objects.filter(data=data_fechamento).first()
    if info_dia:
        total_entregas_salvo = info_dia.quantidade_entregas
        taxa_entrega_salva = info_dia.taxa_entrega
    else:
        total_entregas_salvo = total_entregas_dia  # Fallback para o sugerido
        taxa_entrega_salva = Decimal('9.00')

    if request.method == 'POST':
        desconto_dia_str = request.POST.get('desconto_dia', '0.00').replace(',', '.')
        try:
            desconto_dia = Decimal(desconto_dia_str)
        except:
            desconto_dia = Decimal('0.00')

        entregas_str = request.POST.get('quantidade_entregas', '')
        try:
            quantidade_entregas = int(entregas_str)
        except ValueError:
            quantidade_entregas = total_entregas_dia
            
        taxa_entrega_str = request.POST.get('taxa_entrega', '9.00').replace(',', '.')
        try:
            taxa_entrega = Decimal(taxa_entrega_str)
        except:
            taxa_entrega = Decimal('9.00')
            
        # Salva as info extras do dia
        FechamentoDiarioInfo.objects.update_or_create(
            data=data_fechamento,
            defaults={
                'quantidade_entregas': quantidade_entregas,
                'taxa_entrega': taxa_entrega
            }
        )

        # Agrupa itens postados por (canal_id, forma_pagamento)
        # Campos de formulário com nome "qtd_<produto_id>_<canal_id>_<forma_pagamento>"
        vendas_postadas = {} # {(canal_id, forma_pagamento): [(produto, quantidade, preco_unitario)]}

        for key, val in request.POST.items():
            if key.startswith('qtd_') and val and val.isdigit() and int(val) > 0:
                partes = key.split('_', 3) # ['qtd', 'prod_id', 'canal_id', 'forma_pagamento_id']
                if len(partes) >= 4:
                    prod_id = int(partes[1])
                    canal_id = int(partes[2])
                    forma_pagamento_id = int(partes[3])
                    qtd = int(val)

                    prod_obj = Produto.objects.filter(id=prod_id).first()
                    if prod_obj:
                        preco_unit = precos_matriz.get(prod_id, {}).get(canal_id, Decimal('0.00'))
                        par = (canal_id, forma_pagamento_id)
                        if par not in vendas_postadas:
                            vendas_postadas[par] = []
                        vendas_postadas[par].append((prod_obj, qtd, preco_unit))

        # Cancela/apaga pedidos de fechamento antigos daquela data para recalcular do zero com segurança
        for ped_antigo in pedidos_dia.filter(cliente_nome__icontains='Fechamento Diário'):
            ped_antigo.status = 'CANCELADO'
            ped_antigo.save() # dispara estorno de estoque se baixado
            ped_antigo.delete()

        # Cria novos pedidos por canal e forma de pagamento
        novos_pedidos_criados = 0
        for (canal_id, forma_pagamento_id), itens_lista in vendas_postadas.items():
            canal_obj = CanalVenda.objects.filter(id=canal_id).first()
            forma_pagamento_obj = FormaPagamento.objects.filter(id=forma_pagamento_id).first()
            
            if not canal_obj or not forma_pagamento_obj:
                continue

            # Busca taxa da forma de pagamento
            taxa_obj = TaxaFormaPagamento.objects.filter(canal=canal_obj, forma_pagamento=forma_pagamento_obj).first()
            taxa_pct = taxa_obj.taxa_comissao if taxa_obj else canal_obj.taxa_comissao

            novo_pedido = Pedido.objects.create(
                cliente_nome=f"Fechamento Diário ({forma_pagamento_obj.nome})",
                canal=canal_obj,
                forma_pagamento=forma_pagamento_obj,
                status='CONCLUIDO',
                desconto=desconto_dia,
                data_criacao=timezone.make_aware(datetime.combine(data_fechamento, datetime.now().time()))
            )

            for prod_obj, qtd, preco_unit in itens_lista:
                PedidoItem.objects.create(
                    pedido=novo_pedido,
                    produto=prod_obj,
                    quantidade=qtd,
                    preco_unitario=preco_unit
                )

            # Recalcula valores usando a taxa específica
            novo_pedido.recalcular_valores_financeiros(save=False)
            # Sobrescreve a taxa com a taxa específica da forma de pagamento
            novo_pedido.taxas_canal = (novo_pedido.valor_bruto * taxa_pct).quantize(Decimal('0.01'))
            novo_pedido.lucro_liquido = (novo_pedido.valor_bruto - novo_pedido.taxas_canal - novo_pedido.custo_ingredientes - novo_pedido.desconto).quantize(Decimal('0.01'))
            novo_pedido.save()
            
            # Baixa o estoque automaticamente
            novo_pedido.processar_baixa_estoque()
            novos_pedidos_criados += 1

        messages.success(request, f"Fechamento diário do dia {data_fechamento.strftime('%d/%m/%Y')} gravado com sucesso! ({novos_pedidos_criados} modalidades/canais processados).")
        return redirect(f"{request.path}?data={data_str}")

    context = {
        'data_fechamento': data_str,
        'data_fechamento_obj': data_fechamento,
        'busca': busca,
        'categoria_selecionada': categoria_filtro,
        'produtos': produtos,
        'canais': canais,
        'precos_matriz': precos_matriz,
        'vendas_gravadas': vendas_gravadas,
        'desconto_dia': desconto_dia,
        'quantidade_entregas': total_entregas_salvo,
        'taxa_entrega': taxa_entrega_salva,
        'total_entregas_sugerido': total_entregas_dia,
        'valor_entregas_calculado': (Decimal(total_entregas_salvo) * taxa_entrega_salva).quantize(Decimal('0.02')),
        'categorias': Produto.CATEGORIAS,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'vendas/partials/fechamento_tabela.html', context)

    return render(request, 'vendas/fechamento_diario.html', context)


