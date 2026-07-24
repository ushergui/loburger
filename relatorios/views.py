import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count, F, Q
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime

from core.decorators import gestao_required
from vendas.models import Pedido, PedidoItem, CanalVenda
from produtos.models import Produto
from .models import Despesa
from .forms import DespesaForm

import csv
import calendar
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count, F, Q
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime

from core.decorators import gestao_required
from vendas.models import Pedido, PedidoItem, CanalVenda
from produtos.models import Produto
from .models import Despesa
from .forms import DespesaForm

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

    # 1. Filtrar pedidos concluídos no período exato
    pedidos_concluidos = Pedido.objects.filter(status='CONCLUIDO', data_criacao__range=(data_inicio, data_fim))
    
    # 2. Calcular KPIs do Scorecard
    kpis = pedidos_concluidos.aggregate(
        faturamento_bruto=Sum('valor_bruto'),
        total_pedidos=Count('id'),
        taxas_totais=Sum('taxas_canal'),
        custo_insumos=Sum('custo_ingredientes'),
        lucro_liquido_total=Sum('lucro_liquido')
    )
    
    # Formatação de valores padrões caso o banco esteja vazio
    faturamento = kpis['faturamento_bruto'] or Decimal('0.00')
    num_pedidos = kpis['total_pedidos'] or 0
    taxas = kpis['taxas_totais'] or Decimal('0.00')
    custo = kpis['custo_insumos'] or Decimal('0.00')
    
    # 3. Calcular custos e lucro líquido deduzindo as despesas lançadas no período
    soma_despesas = Despesa.objects.filter(
        data_pagamento__range=(data_inicio.date(), data_fim.date())
    ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
    
    custo_total_kpi = taxas + custo + soma_despesas
    lucro_pedidos = kpis['lucro_liquido_total'] or Decimal('0.00')
    lucro = lucro_pedidos - soma_despesas
    
    ticket = (faturamento / num_pedidos) if num_pedidos > 0 else Decimal('0.00')

    # 4. Dados para o Gráfico 1: Faturamento Diário (Linha)
    faturamento_diario = (
        pedidos_concluidos.extra(select={'dia': "date(data_criacao)"})
        .values('dia')
        .annotate(total=Sum('valor_bruto'), lucro=Sum('lucro_liquido'))
        .order_by('dia')
    )
    chart_dias_labels = [d['dia'] for d in faturamento_diario]
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
        'custo': custo,
        'custo_total_kpi': custo_total_kpi,
        'despesas_total': soma_despesas,
        'lucro': lucro,
        'ticket': ticket,
        
        # Dados estruturados para Chart.js
        'chart_dias_labels': chart_dias_labels,
        'chart_dias_valores': chart_dias_valores,
        'chart_dias_lucro': chart_dias_lucro,
        'chart_canais_labels': chart_canais_labels,
        'chart_canais_valores': chart_canais_valores,
        'chart_canais_lucro': chart_canais_lucro,
        'chart_produtos_labels': chart_produtos_labels,
        'chart_produtos_valores': chart_produtos_valores,
        'produtos_margem': lista_produtos_margem
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
        'Data Criação', 
        'Canal de Venda', 
        'Forma de Pagamento',
        'Invocador (Cliente)', 
        'Faturamento Bruto (R$)', 
        'Taxas do Canal (R$)', 
        'Custo Insumos (R$)', 
        'Lucro Líquido Real (R$)'
    ])
    
    for p in pedidos:
        writer.writerow([
            p.id,
            p.data_criacao.strftime('%d/%m/%Y %H:%M:%S'),
            p.canal.nome,
            p.get_forma_pagamento_display(),
            p.cliente_nome or 'Cliente Avulso',
            str(p.valor_bruto).replace('.', ','),
            str(p.taxas_canal).replace('.', ','),
            str(p.custo_ingredientes).replace('.', ','),
            str(p.lucro_liquido).replace('.', ',')
        ])
        
    return response


@login_required
@gestao_required
def despesa_listar(request):
    busca = request.GET.get('busca', '')
    tipo_filtro = request.GET.get('tipo', '')
    categoria_filtro = request.GET.get('categoria', '')
    
    despesas = Despesa.objects.all()
    
    if busca:
        despesas = despesas.filter(Q(descricao__icontains=busca) | Q(observacao__icontains=busca))
        
    if tipo_filtro:
        despesas = despesas.filter(tipo=tipo_filtro)
        
    if categoria_filtro:
        despesas = despesas.filter(categoria=categoria_filtro)
        
    paginator = Paginator(despesas, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Soma total das despesas filtradas
    total_despesas_filtradas = despesas.aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
    
    context = {
        'page_obj': page_obj,
        'busca': busca,
        'tipo_selecionado': tipo_filtro,
        'categoria_selecionada': categoria_filtro,
        'total_filtrado': total_despesas_filtradas,
        'categorias': Despesa.CATEGORIA_CHOICES,
        'tipos': Despesa.TIPO_CHOICES,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'relatorios/partials/despesas_tabela.html', context)
        
    return render(request, 'relatorios/despesas_lista.html', context)


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
            form.save()
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

