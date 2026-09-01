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
from .models import (
    CanalVenda, TaxaFormaPagamento, FormaPagamento, Pedido, PedidoItem,
    FechamentoDiarioInfo, Entregador, EntregaDiaria, ConfiguracaoFinanceira,
)
from .forms import (
    CanalVendaForm, TaxaFormaPagamentoFormSet, FormaPagamentoForm,
    EntregadorForm, ConfiguracaoFinanceiraForm,
)
from .services import sincronizar_despesas_fechamento

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
            messages.success(request, f"Canal de venda '{canal.nome}' cadastrado!")
            return redirect('canal_listar')
    else:
        form = CanalVendaForm()

    return render(request, 'vendas/canal_form.html', {
        'form': form,
        'titulo': "Cadastrar Canal de Venda"
    })


@login_required
@gestao_required
def canal_editar(request, pk):
    canal = get_object_or_404(CanalVenda, pk=pk)
    if request.method == 'POST':
        form = CanalVendaForm(request.POST, instance=canal)
        if form.is_valid():
            form.save()
            messages.success(request, f"Canal '{canal.nome}' atualizado!")
            return redirect('canal_listar')
    else:
        form = CanalVendaForm(instance=canal)

    return render(request, 'vendas/canal_form.html', {
        'form': form,
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

def _parse_decimal(valor, padrao=Decimal('0.00')):
    try:
        return Decimal(str(valor).replace('R$', '').replace(' ', '').replace(',', '.').strip())
    except Exception:
        return padrao


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
    config = ConfiguracaoFinanceira.get_solo()
    modos = Pedido.MODO_PAGAMENTO_CHOICES

    canais = list(CanalVenda.objects.all().order_by('nome'))
    produtos = Produto.objects.filter(status=True).annotate(
        ordem_categoria=Case(
            When(categoria='BURGER', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by('ordem_categoria', 'nome').prefetch_related('precos_canais')

    if busca:
        produtos = produtos.filter(Q(nome__icontains=busca) | Q(descricao__icontains=busca))
    if categoria_filtro:
        produtos = produtos.filter(categoria=categoria_filtro)

    # Preços {produto_id: {canal_id: preco}}
    precos_matriz = {p.id: {pc.canal_id: pc.preco for pc in p.precos_canais.all()} for p in produtos}

    # Vendas já gravadas do dia (só as do próprio fechamento) {produto_id: {"<canal_id>_<modo>": qtd}}
    pedidos_fechamento = Pedido.objects.filter(
        data_criacao__date=data_fechamento, status='CONCLUIDO',
        cliente_nome__icontains='Fechamento Diário',
    ).prefetch_related('itens')

    vendas_gravadas = {}
    desconto_dia = Decimal('0.00')
    for ped in pedidos_fechamento:
        if ped.desconto and ped.desconto > desconto_dia:
            desconto_dia = ped.desconto
        chave = f"{ped.canal_id}_{ped.modo_pagamento}"
        for item in ped.itens.all():
            vendas_gravadas.setdefault(item.produto_id, {})
            vendas_gravadas[item.produto_id][chave] = vendas_gravadas[item.produto_id].get(chave, 0) + item.quantidade

    entregadores = list(Entregador.objects.filter(ativo=True))
    entregas_salvas = {e.entregador_id: e.quantidade for e in EntregaDiaria.objects.filter(data=data_fechamento)}

    if request.method == 'POST':
        desconto_dia = _parse_decimal(request.POST.get('desconto_dia', '0'))

        # Entregas por entregador
        for ent in entregadores:
            try:
                q = int(request.POST.get(f'entrega_{ent.id}', 0) or 0)
            except ValueError:
                q = 0
            EntregaDiaria.objects.update_or_create(
                data=data_fechamento, entregador=ent, defaults={'quantidade': max(q, 0)},
            )
            entregas_salvas[ent.id] = max(q, 0)

        # Coleta qtd_<produto_id>_<canal_id>_<modo>
        vendas_postadas = {}
        sem_preco = set()
        for key, val in request.POST.items():
            if not key.startswith('qtd_'):
                continue
            v = val.strip()
            if not v.isdigit() or int(v) <= 0:
                continue
            partes = key.split('_')
            if len(partes) != 4:
                continue
            _, pid, cid, modo = partes
            if modo not in dict(modos):
                continue
            prod_obj = Produto.objects.filter(id=int(pid)).first()
            if not prod_obj:
                continue
            preco_unit = precos_matriz.get(int(pid), {}).get(int(cid), Decimal('0.00'))
            if preco_unit <= 0:
                sem_preco.add(prod_obj.nome)
            vendas_postadas.setdefault((int(cid), modo), []).append((prod_obj, int(v), preco_unit))

        # Recria os pedidos do dia do zero (estorna estoque dos antigos)
        for ped_antigo in Pedido.objects.filter(
            data_criacao__date=data_fechamento, cliente_nome__icontains='Fechamento Diário',
        ):
            ped_antigo.status = 'CANCELADO'
            ped_antigo.save()
            ped_antigo.delete()

        modos_dict = dict(modos)
        n = 0
        desconto_restante = desconto_dia
        for (canal_id, modo), itens_lista in vendas_postadas.items():
            canal_obj = CanalVenda.objects.filter(id=canal_id).first()
            if not canal_obj:
                continue
            # O desconto do dia é aplicado uma única vez (no primeiro pedido criado)
            desconto_pedido = desconto_restante
            desconto_restante = Decimal('0.00')

            novo = Pedido.objects.create(
                cliente_nome=f"Fechamento Diário ({modos_dict.get(modo, modo)})",
                canal=canal_obj, modo_pagamento=modo, status='CONCLUIDO',
                desconto=desconto_pedido,
            )
            # data_criacao é auto_now_add — força a data do fechamento via update
            Pedido.objects.filter(id=novo.id).update(
                data_criacao=timezone.make_aware(datetime.combine(data_fechamento, datetime.now().time()))
            )
            novo.refresh_from_db()
            for prod_obj, qtd, preco_unit in itens_lista:
                PedidoItem.objects.create(pedido=novo, produto=prod_obj, quantidade=qtd, preco_unitario=preco_unit)
            novo.recalcular_valores_financeiros(save=True)
            novo.processar_baixa_estoque()
            n += 1

        # Mantém compatibilidade com FechamentoDiarioInfo (nº de entregas do dia)
        total_entregas = sum(entregas_salvas.values())
        FechamentoDiarioInfo.objects.update_or_create(
            data=data_fechamento,
            defaults={'quantidade_entregas': total_entregas, 'taxa_entrega': config.taxa_entrega},
        )

        # Gera as despesas automáticas do dia (taxas + motoboy)
        qtd_despesas = sincronizar_despesas_fechamento(data_fechamento)

        msg = (f"Fechamento de {data_fechamento.strftime('%d/%m/%Y')} gravado: "
               f"{n} combinações de canal/pagamento, {qtd_despesas} lançamentos automáticos de despesa.")
        if sem_preco:
            messages.warning(request, msg + f" Atenção: sem preço cadastrado para {', '.join(sorted(sem_preco))} — lançado como R$ 0,00.")
        else:
            messages.success(request, msg)
        return redirect(f"{request.path}?data={data_str}")

    # Estrutura pronta para o template: colunas (canal x modo) e linhas (produto x células)
    colunas = [
        {'canal': c, 'modo': m_val, 'modo_label': m_label}
        for c in canais for m_val, m_label in modos
    ]
    linhas = []
    for p in produtos:
        celulas = []
        gravadas_p = vendas_gravadas.get(p.id, {})
        for c in canais:
            preco = precos_matriz.get(p.id, {}).get(c.id, Decimal('0.00'))
            for m_val, _m_label in modos:
                celulas.append({
                    'name': f"qtd_{p.id}_{c.id}_{m_val}",
                    'qtd': gravadas_p.get(f"{c.id}_{m_val}", ''),
                    'preco': preco,
                })
        linhas.append({'produto': p, 'celulas': celulas})

    total_entregas_salvo = sum(entregas_salvas.values())
    context = {
        'data_fechamento': data_str,
        'data_fechamento_obj': data_fechamento,
        'busca': busca,
        'categoria_selecionada': categoria_filtro,
        'canais': canais,
        'modos': modos,
        'colunas': colunas,
        'linhas': linhas,
        'num_modos': len(modos),
        'desconto_dia': desconto_dia,
        'entregadores': [{'obj': e, 'qtd': entregas_salvas.get(e.id, 0)} for e in entregadores],
        'taxa_entrega': config.taxa_entrega,
        'total_entregas_salvo': total_entregas_salvo,
        'valor_entregas_calculado': (Decimal(total_entregas_salvo) * config.taxa_entrega).quantize(Decimal('0.01')),
        'categorias': Produto.CATEGORIAS,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'vendas/partials/fechamento_tabela.html', context)

    return render(request, 'vendas/fechamento_diario.html', context)


# ==========================================
# ENTREGADORES (GESTÃO)
# ==========================================

@login_required
@gestao_required
def entregador_listar(request):
    entregadores = Entregador.objects.all()
    return render(request, 'vendas/entregador_lista.html', {'entregadores': entregadores})


@login_required
@gestao_required
def entregador_criar(request):
    if request.method == 'POST':
        form = EntregadorForm(request.POST)
        if form.is_valid():
            e = form.save()
            messages.success(request, f"Entregador '{e.nome}' cadastrado!")
            return redirect('entregador_listar')
    else:
        form = EntregadorForm()
    return render(request, 'vendas/entregador_form.html', {'form': form, 'titulo': "Cadastrar Entregador"})


@login_required
@gestao_required
def entregador_editar(request, pk):
    e = get_object_or_404(Entregador, pk=pk)
    if request.method == 'POST':
        form = EntregadorForm(request.POST, instance=e)
        if form.is_valid():
            form.save()
            messages.success(request, f"Entregador '{e.nome}' atualizado!")
            return redirect('entregador_listar')
    else:
        form = EntregadorForm(instance=e)
    return render(request, 'vendas/entregador_form.html', {'form': form, 'titulo': f"Editar Entregador: {e.nome}"})


@login_required
@gestao_required
def entregador_excluir(request, pk):
    e = get_object_or_404(Entregador, pk=pk)
    if request.method == 'POST':
        nome = e.nome
        try:
            e.delete()
            messages.success(request, f"Entregador '{nome}' excluído.")
        except Exception:
            messages.error(request, "Não é possível excluir: este entregador já tem entregas registradas. Marque como inativo.")
        return redirect('entregador_listar')
    return render(request, 'vendas/entregador_confirm_delete.html', {'entregador': e})


# ==========================================
# CONFIGURAÇÃO FINANCEIRA (GESTÃO)
# ==========================================

@login_required
@gestao_required
def configuracao_financeira(request):
    config = ConfiguracaoFinanceira.get_solo()
    if request.method == 'POST':
        form = ConfiguracaoFinanceiraForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração financeira atualizada. Vale para os próximos lançamentos.")
            return redirect('configuracao_financeira')
    else:
        form = ConfiguracaoFinanceiraForm(instance=config)
    return render(request, 'vendas/configuracao_financeira.html', {'form': form, 'titulo': "Configuração Financeira"})


