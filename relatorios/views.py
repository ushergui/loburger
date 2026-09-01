import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count, F, Q
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime, date
import calendar

from core.decorators import gestao_required
from vendas.models import Pedido, PedidoItem, CanalVenda
from produtos.models import Produto
from .models import Despesa, DespesaRecorrente, CATEGORIA_CHOICES, CATEGORIAS_AUTOMATICAS
from .forms import DespesaForm, DespesaRecorrenteForm
from . import services

MESES_PROJECAO_PADRAO = 12


def gerar_despesas_fixas_pendentes(meses_a_frente=MESES_PROJECAO_PADRAO):
    """Gera as faturas previstas dos moldes fixos: mês atual + N meses à frente.
    Nunca gera nada para trás."""
    hoje = timezone.localdate()
    y, m = hoje.year, hoje.month
    meses_para_gerar = []
    for _ in range(meses_a_frente + 1):
        meses_para_gerar.append(date(y, m, 1))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    for molde in DespesaRecorrente.objects.filter(ativa=True):
        for mes_ref in meses_para_gerar:
            try:
                data_venc = mes_ref.replace(day=molde.dia_vencimento)
            except ValueError:
                ultimo_dia = calendar.monthrange(mes_ref.year, mes_ref.month)[1]
                data_venc = mes_ref.replace(day=ultimo_dia)

            existe = Despesa.objects.filter(
                despesa_matriz=molde,
                data_vencimento__year=data_venc.year,
                data_vencimento__month=data_venc.month,
            ).exists()

            if not existe:
                Despesa.objects.create(
                    descricao=molde.descricao,
                    tipo='FIXO',
                    categoria=molde.categoria,
                    valor=molde.valor_base,
                    status='PREVISTO',
                    data_vencimento=data_venc,
                    despesa_matriz=molde,
                    origem='RECORRENTE',
                    observacao=f"Gerada automaticamente pelo molde {molde.id}.",
                )

MESES_PT = {
    1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
    5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
    9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
}

def obter_datas_filtro(periodo_param, mes_param):
    agora = timezone.now()
    hoje_date = timezone.localdate()
    
    # Se nem periodo nem mes foram passados, o padrão absoluto é o MÊS ATUAL
    if not periodo_param and not mes_param:
        periodo_param = 'mes_atual'

    ano_sel, mes_sel = hoje_date.year, hoje_date.month
    tipo_filtro = 'mes'
    
    if mes_param and len(mes_param.split('-')) == 2:
        try:
            ano_sel, mes_sel = map(int, mes_param.split('-'))
            periodo_param = 'mes_especifico'
        except ValueError:
            ano_sel, mes_sel = hoje_date.year, hoje_date.month

    if periodo_param == 'hoje':
        data_inicio = timezone.make_aware(datetime.combine(hoje_date, datetime.min.time()))
        data_fim = timezone.make_aware(datetime.combine(hoje_date, datetime.max.time()))
        label_periodo = f"Hoje ({hoje_date.strftime('%d/%m/%Y')})"
        tipo_filtro = 'hoje'
        mes_val = f"{hoje_date.year:04d}-{hoje_date.month:02d}"
    elif periodo_param == '7':
        data_inicio = agora - timedelta(days=7)
        data_fim = agora
        label_periodo = "Últimos 7 dias"
        tipo_filtro = '7'
        mes_val = f"{hoje_date.year:04d}-{hoje_date.month:02d}"
    elif periodo_param == '30':
        data_inicio = agora - timedelta(days=30)
        data_fim = agora
        label_periodo = "Últimos 30 dias"
        tipo_filtro = '30'
        mes_val = f"{hoje_date.year:04d}-{hoje_date.month:02d}"
    elif periodo_param == 'todos':
        data_inicio = timezone.make_aware(datetime(2020, 1, 1, 0, 0, 0))
        data_fim = agora
        label_periodo = "Todos os Tempos"
        tipo_filtro = 'todos'
        mes_val = f"{hoje_date.year:04d}-{hoje_date.month:02d}"
    elif periodo_param == 'mes_anterior':
        if hoje_date.month == 1:
            ano_sel, mes_sel = hoje_date.year - 1, 12
        else:
            ano_sel, mes_sel = hoje_date.year, hoje_date.month - 1
        ultimo_dia = calendar.monthrange(ano_sel, mes_sel)[1]
        data_inicio = timezone.make_aware(datetime(ano_sel, mes_sel, 1, 0, 0, 0))
        data_fim = timezone.make_aware(datetime(ano_sel, mes_sel, ultimo_dia, 23, 59, 59, 999999))
        label_periodo = f"{MESES_PT.get(mes_sel, '')} de {ano_sel}"
        tipo_filtro = 'mes'
        mes_val = f"{ano_sel:04d}-{mes_sel:02d}"
        periodo_param = 'mes_especifico'
    else: # mes_atual ou mes_especifico
        ultimo_dia = calendar.monthrange(ano_sel, mes_sel)[1]
        data_inicio = timezone.make_aware(datetime(ano_sel, mes_sel, 1, 0, 0, 0))
        data_fim = timezone.make_aware(datetime(ano_sel, mes_sel, ultimo_dia, 23, 59, 59, 999999))
        label_periodo = f"{MESES_PT.get(mes_sel, '')} de {ano_sel}"
        tipo_filtro = 'mes'
        mes_val = f"{ano_sel:04d}-{mes_sel:02d}"
        if not mes_param and ano_sel == hoje_date.year and mes_sel == hoje_date.month:
            periodo_param = 'mes_atual'

    return data_inicio, data_fim, tipo_filtro, label_periodo, ano_sel, mes_sel, mes_val, periodo_param


@login_required
@gestao_required
def dashboard(request):
    gerar_despesas_fixas_pendentes()
    
    periodo_param = request.GET.get('periodo', '').strip()
    mes_param = request.GET.get('mes', '').strip()
    hoje_date = timezone.localdate()
    
    data_inicio, data_fim, tipo_filtro, label_periodo, ano_sel, mes_sel, mes_val, periodo = obter_datas_filtro(periodo_param, mes_param)

    # Navegação Mês a Mês (Mês anterior e próximo mês)
    if mes_sel == 1:
        ano_ant, mes_ant = ano_sel - 1, 12
    else:
        ano_ant, mes_ant = ano_sel, mes_sel - 1
    mes_anterior_val = f"{ano_ant:04d}-{mes_ant:02d}"

    if mes_sel == 12:
        ano_prox, mes_prox = ano_sel + 1, 1
    else:
        ano_prox, mes_prox = ano_sel, mes_sel + 1
    mes_proximo_val = f"{ano_prox:04d}-{mes_prox:02d}"
    mes_atual_val = f"{hoje_date.year:04d}-{hoje_date.month:02d}"

    # Dropdown com os últimos 12 meses
    opcoes_meses = []
    cur_y, cur_m = hoje_date.year, hoje_date.month
    for i in range(12):
        v_str = f"{cur_y:04d}-{cur_m:02d}"
        l_str = f"{MESES_PT.get(cur_m, '')} / {cur_y}"
        opcoes_meses.append({'value': v_str, 'label': l_str})
        if cur_m == 1:
            cur_y -= 1
            cur_m = 12
        else:
            cur_m -= 1

    # 1. Filtrar pedidos concluídos no período exato (usado nos gráficos)
    pedidos_concluidos = Pedido.objects.filter(status='CONCLUIDO', data_criacao__range=(data_inicio, data_fim))

    # 2. Consolidação financeira do período (regime de caixa)
    resumo = services.resumo_financeiro(data_inicio.date(), data_fim.date())
    mov = services.resumo_movimentacao_estoque(data_inicio.date(), data_fim.date())

    faturamento = resumo['faturamento_bruto']
    num_pedidos = resumo['num_pedidos']
    taxas_plataforma = resumo['taxas_plataforma']
    custo = resumo['cmv']
    ticket = resumo['ticket_medio']
    resultado_caixa = resumo['resultado_caixa']
    resultado_operacional = resumo['resultado_operacional']
    lucro_economico = resumo['lucro_economico']
    despesas_total = resumo['despesas_pagas_total']
    compras_insumo = resumo['compras_insumo']
    retiradas_socios = resumo['retiradas_socios']

    # "Foto" da empresa — não zera no fim do mês
    caixa_hoje = services.caixa_acumulado()
    valor_estoque_hoje = services.valor_estoque_atual()

    # Compatibilidade com nomes antigos usados no template / gráficos
    lucro = resultado_caixa
    taxas = taxas_plataforma
    taxas_cartao = Decimal('0.00')
    soma_despesas = despesas_total
    custo_total_kpi = despesas_total

    # Alertas de Vencimento de Despesas (Próximos 5 dias ou atrasadas)
    hoje_venc = timezone.localdate()
    cinco_dias = hoje_venc + timedelta(days=5)
    despesas_vencimento_proximo = Despesa.objects.filter(
        status='PREVISTO',
        data_vencimento__lte=cinco_dias,
        data_vencimento__gte=hoje_venc - timedelta(days=30) # não mostrar coisas super antigas
    ).order_by('data_vencimento')

    # 4. Dados para o Gráfico 1: Faturamento Diário (Linha)
    from django.db.models.functions import TruncDate
    faturamento_diario = (
        pedidos_concluidos.annotate(dia=TruncDate('data_criacao'))
        .values('dia')
        .annotate(total=Sum('valor_bruto'), lucro=Sum('lucro_liquido'))
        .order_by('dia')
    )
    chart_dias_labels = [d['dia'].strftime('%d/%m') if d['dia'] else '' for d in faturamento_diario]
    chart_dias_valores = [float(d['total']) for d in faturamento_diario]
    chart_dias_lucro = [float(d['lucro']) for d in faturamento_diario]

    # 5. Dados para o Gráfico 2: Vendas por Canal (Rosca/Pizza)
    vendas_por_canal = (
        pedidos_concluidos.values('canal__nome')
        .annotate(total=Sum('valor_bruto'), lucro=Sum('lucro_liquido'), count=Count('id'))
        .order_by('-total')
    )
    chart_canais_labels = [c['canal__nome'] for c in vendas_por_canal]
    chart_canais_valores = [float(c['total']) for c in vendas_por_canal]
    chart_canais_lucro = [float(c['lucro']) for c in vendas_por_canal]

    # 6. Dados para o Gráfico 3: Ranking dos Campeões (Barras)
    itens_vendidos = (
        PedidoItem.objects.filter(pedido__status='CONCLUIDO', pedido__data_criacao__range=(data_inicio, data_fim))
        .values('produto__nome')
        .annotate(qtd=Sum('quantidade'))
        .order_by('-qtd')[:5]
    )
    chart_produtos_labels = [p['produto__nome'] for p in itens_vendidos]
    chart_produtos_valores = [p['qtd'] for p in itens_vendidos]

    # 7. Margem de lucro média dos produtos
    produtos_margem = Produto.objects.filter(status=True).prefetch_related('precos_canais')
    lista_produtos_margem = []
    for prod in produtos_margem[:5]:
        preco_medio = prod.precos_canais.aggregate(avg_price=Sum('preco'))['avg_price'] or Decimal('0.00')
        num_canais = prod.precos_canais.count()
        if num_canais > 0:
            preco_medio = preco_medio / num_canais
        custo_total = prod.custo_total
        margem_valor = preco_medio - custo_total
        margem_pct = (margem_valor / preco_medio * 100) if preco_medio > 0 else Decimal('0.00')
        lista_produtos_margem.append({
            'nome': prod.nome,
            'custo': custo_total,
            'preco_medio': preco_medio,
            'lucro_bruto': margem_valor,
            'margem_pct': margem_pct.quantize(Decimal('0.01'))
        })

    context = {
        'periodo': periodo,
        'mes_selecionado': mes_val,
        'label_periodo': label_periodo,
        'mes_anterior_val': mes_anterior_val,
        'mes_proximo_val': mes_proximo_val,
        'mes_atual_val': mes_atual_val,
        'opcoes_meses': opcoes_meses,
        
        'faturamento': faturamento,
        'num_pedidos': num_pedidos,
        'taxas': taxas,
        'taxas_cartao': taxas_cartao,
        'custo': custo,
        'custo_total_kpi': custo_total_kpi,
        'despesas_total': soma_despesas,
        'lucro': lucro,
        'ticket': ticket,

        # Regime de caixa + ponte para competência
        'resultado_caixa': resultado_caixa,
        'resultado_operacional': resultado_operacional,
        'lucro_economico': lucro_economico,
        'compras_insumo': compras_insumo,
        'retiradas_socios': retiradas_socios,
        'receita_entregas': resumo['receita_entregas'],
        'autoconsumo_mes': mov['autoconsumo'],
        'perdas_mes': mov['perdas'],

        # "Foto" da empresa (não zera no mês)
        'caixa_hoje': caixa_hoje,
        'valor_estoque_hoje': valor_estoque_hoje,


        # Dados estruturados para Chart.js
        'chart_dias_labels': chart_dias_labels,
        'chart_dias_valores': chart_dias_valores,
        'chart_dias_lucro': chart_dias_lucro,
        'chart_canais_labels': chart_canais_labels,
        'chart_canais_valores': chart_canais_valores,
        'chart_canais_lucro': chart_canais_lucro,
        'chart_produtos_labels': chart_produtos_labels,
        'chart_produtos_valores': chart_produtos_valores,
        'produtos_margem': lista_produtos_margem,
        'despesas_vencimento_proximo': despesas_vencimento_proximo,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'relatorios/partials/dashboard_dados.html', context)
        
    return render(request, 'relatorios/dashboard.html', context)


@login_required
@gestao_required
def exportar_csv(request):
    periodo_param = request.GET.get('periodo', '').strip()
    mes_param = request.GET.get('mes', '').strip()
    
    data_inicio, data_fim, tipo_filtro, label_periodo, ano_sel, mes_sel, mes_val, periodo = obter_datas_filtro(periodo_param, mes_param)
    
    pedidos = Pedido.objects.filter(status='CONCLUIDO', data_criacao__range=(data_inicio, data_fim)).select_related('canal').order_by('data_criacao')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="lolburger_relatorio_{mes_val}.csv"'
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'ID Pedido', 
        'Data',
        'Canal de Venda',
        'Modo de Pagamento',
        'Descrição',
        'Faturamento Bruto (R$)',
        'Comissão da Plataforma (R$)',
        'Taxa de Pagamento (R$)',
        'CMV Informativo (R$)',
        'Líquido Recebido (R$)'
    ])

    for p in pedidos:
        writer.writerow([
            p.id,
            p.data_criacao.strftime('%d/%m/%Y %H:%M:%S'),
            p.canal.nome,
            p.get_modo_pagamento_display(),
            p.cliente_nome or 'Venda',
            str(p.valor_bruto).replace('.', ','),
            str(p.taxas_canal).replace('.', ','),
            str(p.taxas_pagamento).replace('.', ','),
            str(p.custo_ingredientes).replace('.', ','),
            str(p.lucro_liquido).replace('.', ',')
        ])
        
    return response


@login_required
@gestao_required
def despesa_listar(request):
    gerar_despesas_fixas_pendentes()

    busca = request.GET.get('busca', '')
    tipo_filtro = request.GET.get('tipo', '')
    categoria_filtro = request.GET.get('categoria', '')
    vista = request.GET.get('vista', 'a_pagar')  # a_pagar | pagas

    despesas = Despesa.objects.all()
    if vista == 'pagas':
        despesas = despesas.filter(status='PAGO').order_by('-data_pagamento', '-id')
    else:
        vista = 'a_pagar'
        despesas = despesas.filter(status='PREVISTO').order_by('data_vencimento')

    if busca:
        despesas = despesas.filter(Q(descricao__icontains=busca) | Q(observacao__icontains=busca))
    if tipo_filtro:
        despesas = despesas.filter(tipo=tipo_filtro)
    if categoria_filtro:
        despesas = despesas.filter(categoria=categoria_filtro)

    paginator = Paginator(despesas, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    total_despesas_filtradas = despesas.aggregate(total=Sum('valor'))['total'] or Decimal('0.00')

    # Contadores para as abas
    hoje = timezone.localdate()
    qs_prev = Despesa.objects.filter(status='PREVISTO')
    total_a_pagar = qs_prev.aggregate(t=Sum('valor'))['t'] or Decimal('0.00')
    total_atrasadas = qs_prev.filter(data_vencimento__lt=hoje).count()

    context = {
        'page_obj': page_obj,
        'vista': vista,
        'busca': busca,
        'tipo_selecionado': tipo_filtro,
        'categoria_selecionada': categoria_filtro,
        'total_filtrado': total_despesas_filtradas,
        'total_a_pagar': total_a_pagar,
        'total_atrasadas': total_atrasadas,
        'hoje': hoje,
        'categorias': CATEGORIA_CHOICES,
        'tipos': Despesa.TIPO_CHOICES,
        'recorrentes': DespesaRecorrente.objects.all(),
    }

    if request.headers.get('HX-Request'):
        return render(request, 'relatorios/partials/despesas_tabela.html', context)

    return render(request, 'relatorios/despesas_lista.html', context)


@login_required
@gestao_required
def despesa_marcar_paga(request, id):
    despesa = get_object_or_404(Despesa, id=id)
    if request.method == 'POST':
        data_str = request.POST.get('data_pagamento', '').strip()
        try:
            dp = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else timezone.localdate()
        except ValueError:
            dp = timezone.localdate()
        despesa.data_pagamento = dp
        despesa.status = 'PAGO'
        despesa.save()
        messages.success(request, f"'{despesa.descricao}' marcada como paga em {dp.strftime('%d/%m/%Y')}. Saiu do caixa nesse dia.")
    return redirect('despesa_listar')


@login_required
@gestao_required
def despesa_criar(request):
    if request.method == 'POST':
        form = DespesaForm(request.POST)
        if form.is_valid():
            despesa = form.save()
            messages.success(request, f"Despesa '{despesa.descricao}' no valor de R$ {despesa.valor} cadastrada com sucesso!")
            return redirect('despesa_listar')
    else:
        form = DespesaForm()
        
    return render(request, 'relatorios/despesa_form.html', {
        'form': form,
        'titulo': "Lançar Nova Despesa / Custo"
    })


@login_required
@gestao_required
def despesa_editar(request, id):
    despesa = get_object_or_404(Despesa, id=id)
    if request.method == 'POST':
        form = DespesaForm(request.POST, instance=despesa)
        if form.is_valid():
            desp = form.save()
            
            # Lógica para alterar o template e despesas futuras
            if form.cleaned_data.get('alterar_futuros') and desp.despesa_matriz:
                matriz = desp.despesa_matriz
                matriz.valor_base = desp.valor
                matriz.dia_vencimento = desp.data_vencimento.day
                matriz.save()
                
                # Atualiza as despesas geradas (PREVISTAS) no futuro
                Despesa.objects.filter(
                    despesa_matriz=matriz,
                    status='PREVISTO',
                    data_vencimento__gt=desp.data_vencimento
                ).update(
                    valor=desp.valor,
                    data_vencimento=F('data_vencimento') # Manter o mês e ano, apenas o dia será alterado via um map?
                    # Nota: Mudar o 'day' no banco diretamente não é tão simples via update(). 
                    # Vamos fazer num loop para ser preciso.
                )
                
                # Corrigindo o dia das faturas futuras
                futuras = Despesa.objects.filter(despesa_matriz=matriz, status='PREVISTO', data_vencimento__gt=desp.data_vencimento)
                for fut in futuras:
                    try:
                        fut.data_vencimento = fut.data_vencimento.replace(day=matriz.dia_vencimento)
                    except ValueError:
                        ultimo_dia = calendar.monthrange(fut.data_vencimento.year, fut.data_vencimento.month)[1]
                        fut.data_vencimento = fut.data_vencimento.replace(day=ultimo_dia)
                    fut.valor = matriz.valor_base
                    fut.save()
                    
            messages.success(request, f"Despesa '{despesa.descricao}' atualizada com sucesso!")
            return redirect('despesa_listar')
    else:
        form = DespesaForm(instance=despesa)
        
    return render(request, 'relatorios/despesa_form.html', {
        'form': form,
        'titulo': f"Editar Despesa: {despesa.descricao}"
    })


@login_required
@gestao_required
def despesa_excluir(request, id):
    despesa = get_object_or_404(Despesa, id=id)
    if request.method == 'POST':
        descricao = despesa.descricao
        despesa.delete()
        messages.success(request, f"Despesa '{descricao}' excluída com sucesso!")
        return redirect('despesa_listar')
        
    return render(request, 'relatorios/despesa_confirm_delete.html', {
        'despesa': despesa
    })

@login_required
@gestao_required
def despesa_recorrente_criar(request):
    if request.method == 'POST':
        form = DespesaRecorrenteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Despesa Fixa (Molde) cadastrada com sucesso! Faturas serão geradas automaticamente.")
            return redirect('despesa_listar')
    else:
        form = DespesaRecorrenteForm()
        
    return render(request, 'relatorios/despesa_recorrente_form.html', {
        'form': form,
        'titulo': "Cadastrar Despesa Fixa Recorrente"
    })

@login_required
@gestao_required
def despesa_recorrente_editar(request, id):
    molde = get_object_or_404(DespesaRecorrente, id=id)
    if request.method == 'POST':
        form = DespesaRecorrenteForm(request.POST, instance=molde)
        if form.is_valid():
            form.save()
            messages.success(request, "Despesa Fixa (Molde) atualizada com sucesso!")
            return redirect('despesa_listar')
    else:
        form = DespesaRecorrenteForm(instance=molde)
        
    return render(request, 'relatorios/despesa_recorrente_form.html', {
        'form': form,
        'titulo': f"Editar Molde: {molde.descricao}"
    })

@login_required
@gestao_required
def despesa_recorrente_excluir(request, id):
    molde = get_object_or_404(DespesaRecorrente, id=id)
    if request.method == 'POST':
        Despesa.objects.filter(despesa_matriz=molde, status='PREVISTO').delete()
        molde.delete()
        messages.success(request, "Despesa Fixa (Molde) e faturas previstas futuras excluídas com sucesso!")
        return redirect('despesa_listar')
        
    return render(request, 'relatorios/despesa_recorrente_confirm_delete.html', {'molde': molde})

@login_required
@gestao_required
def notificacoes_badge(request):
    hoje = timezone.localdate()
    cinco_dias = hoje + timedelta(days=5)
    despesas_vencimento = Despesa.objects.filter(
        status='PREVISTO',
        data_vencimento__lte=cinco_dias,
        data_vencimento__gte=hoje - timedelta(days=30)
    ).order_by('data_vencimento')
    
    qtd = despesas_vencimento.count()
    
    return render(request, 'relatorios/partials/notificacoes_badge.html', {
        'qtd': qtd,
        'despesas': despesas_vencimento[:5] # mostra no max as top 5
    })

