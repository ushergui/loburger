import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime, date
import calendar

from core.decorators import gestao_required
from vendas.models import Pedido, PedidoItem, CanalVenda
from produtos.models import Produto
from .models import (
    Despesa, DespesaRecorrente, CATEGORIA_CHOICES, CATEGORIAS_AUTOMATICAS,
    FREQUENCIA_CHOICES, tipo_por_categoria, avancar_data,
)
from .forms import DespesaForm, DespesaRecorrenteForm
from . import services

MESES_PROJECAO_PADRAO = 12
DIAS_ALERTA_URGENTE = 3   # badge do sino: atrasadas + vence em ≤ 3 dias
DIAS_ALERTA_LISTA = 7     # o que aparece na lista de "próximas"


def _horizonte_recorrente(rec, hoje):
    """Até quando adiantar as contas previstas de uma recorrente. É uma JANELA
    ROLANTE: a geração roda todo dia e empurra o horizonte pra frente, então a
    recorrente é perpétua — o usuário nunca precisa recadastrar. O horizonte só
    limita quantas contas ficam "prontas" na lista de uma vez."""
    if rec.frequencia in ('SEMANAL', 'QUINZENAL'):
        return hoje + timedelta(days=180)     # ~6 meses de contas semanais/quinzenais
    if rec.frequencia == 'ANUAL':
        return hoje + timedelta(days=365 * 4)  # 4 anos
    return hoje + timedelta(days=365 * 2 + 30)  # ~2 anos das mensais/bimestrais...


def gerar_despesas_fixas_pendentes(meses_a_frente=MESES_PROJECAO_PADRAO, forcar=False):
    """Gera as faturas PREVISTAS das despesas recorrentes, do primeiro vencimento
    até o horizonte de cada frequência. Nunca gera nada muito para trás.
    Roda no máximo 1x por dia (guarda em ConfiguracaoFinanceira), salvo forcar=True."""
    from vendas.models import ConfiguracaoFinanceira

    hoje = timezone.localdate()
    config = ConfiguracaoFinanceira.get_solo()
    if not forcar and config.ultima_geracao_recorrentes == hoje:
        return 0

    piso = hoje - timedelta(days=31)  # não recria um monte de contas atrasadas fantasma
    criadas = 0
    for rec in DespesaRecorrente.objects.filter(ativa=True):
        if not rec.primeiro_vencimento:
            continue
        limite = _horizonte_recorrente(rec, hoje)
        d = rec.primeiro_vencimento
        guard = 0
        while d < piso and guard < 4000:
            d = rec.proxima_data(d)
            guard += 1
        while d <= limite and guard < 4000:
            existe = Despesa.objects.filter(despesa_matriz=rec, data_vencimento=d).exists()
            if not existe:
                Despesa.objects.create(
                    descricao=rec.descricao,
                    credor=rec.credor,
                    tipo=tipo_por_categoria(rec.categoria),
                    categoria=rec.categoria,
                    valor=rec.valor_base,
                    status='PREVISTO',
                    data_vencimento=d,
                    despesa_matriz=rec,
                    origem='RECORRENTE',
                    forma_pagamento='OUTRO',
                    observacao=f"Gerada automaticamente pela despesa recorrente #{rec.id}.",
                )
                criadas += 1
            d = rec.proxima_data(d)
            guard += 1

    config.ultima_geracao_recorrentes = hoje
    config.save(update_fields=['ultima_geracao_recorrentes'])
    return criadas


def propagar_molde_para_previstas(molde, a_partir_de=None):
    """Depois de editar uma recorrente: apaga as faturas PREVISTAS ainda não vencidas
    e deixa a próxima geração recriá-las com o novo valor / frequência / datas."""
    hoje = timezone.localdate()
    corte = a_partir_de or hoje
    apagadas = Despesa.objects.filter(
        despesa_matriz=molde, status='PREVISTO', data_vencimento__gte=corte,
    ).delete()[0]
    return apagadas

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

    # Alertas de contas a pagar: atrasadas + próximas (até DIAS_ALERTA_LISTA dias)
    hoje_venc = timezone.localdate()
    despesas_vencimento_proximo = list(
        Despesa.objects.filter(
            status='PREVISTO',
            data_vencimento__lte=hoje_venc + timedelta(days=DIAS_ALERTA_LISTA),
        ).order_by('data_vencimento')
    )
    for d in despesas_vencimento_proximo:
        _rotular_vencimento(d, hoje_venc)

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

    hoje = timezone.localdate()
    # Rótulo de urgência nas contas a pagar
    if vista == 'a_pagar':
        for d in page_obj:
            _rotular_vencimento(d, hoje)

    qs_prev = Despesa.objects.filter(status='PREVISTO')
    total_a_pagar = qs_prev.aggregate(t=Sum('valor'))['t'] or Decimal('0.00')
    total_atrasadas = qs_prev.filter(data_vencimento__lt=hoje).count()
    total_urgentes = contas_a_pagar_urgentes(hoje).count()

    context = {
        'page_obj': page_obj,
        'vista': vista,
        'busca': busca,
        'tipo_selecionado': tipo_filtro,
        'categoria_selecionada': categoria_filtro,
        'total_filtrado': total_despesas_filtradas,
        'total_a_pagar': total_a_pagar,
        'total_atrasadas': total_atrasadas,
        'total_urgentes': total_urgentes,
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
        messages.success(
            request,
            f"'{despesa.descricao}' — R$ {despesa.valor} — marcada como paga em {dp.strftime('%d/%m/%Y')}. "
            "Sai de Contas a Pagar e debita do caixa nesse dia."
        )
        return redirect('despesa_listar')

    return render(request, 'relatorios/despesa_pagar.html', {
        'despesa': despesa,
        'hoje': timezone.localdate().strftime('%Y-%m-%d'),
    })


@login_required
@gestao_required
def despesa_pagar_lote(request):
    """Marca várias contas previstas como pagas de uma vez (ex.: a fatura inteira
    de um cartão), todas com a mesma data de pagamento."""
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        data_str = (request.POST.get('data_pagamento') or '').strip()
        try:
            dp = datetime.strptime(data_str, '%Y-%m-%d').date() if data_str else timezone.localdate()
        except ValueError:
            dp = timezone.localdate()
        qs = list(Despesa.objects.filter(id__in=ids, status='PREVISTO'))
        total = sum((d.valor for d in qs), Decimal('0.00'))
        for d in qs:
            d.data_pagamento = dp
            d.status = 'PAGO'
            d.save()
        if qs:
            messages.success(
                request,
                f"{len(qs)} conta(s) — R$ {total:.2f} — marcada(s) como paga(s) em "
                f"{dp.strftime('%d/%m/%Y')}. Debitado do caixa nesse dia."
            )
        else:
            messages.info(request, "Nenhuma conta selecionada.")
    return redirect('despesa_listar')


@login_required
@gestao_required
def despesa_criar(request):
    if request.method == 'POST':
        form = DespesaForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            parcelas = cd.get('parcelas') or 1

            if parcelas > 1:
                import uuid
                grupo = uuid.uuid4().hex
                total = cd['valor']
                base = (total / parcelas).quantize(Decimal('0.01'))
                desc_base = cd['descricao']
                freq = cd.get('frequencia_parcelas') or 'MENSAL'
                freq_label = dict(FREQUENCIA_CHOICES).get(freq, freq).split(' (')[0].lower()
                for i in range(1, parcelas + 1):
                    valor_i = base if i < parcelas else (total - base * (parcelas - 1))
                    Despesa.objects.create(
                        descricao=f"{desc_base} ({i}/{parcelas})",
                        credor=cd.get('credor', ''),
                        tipo=tipo_por_categoria(cd['categoria']), categoria=cd['categoria'],
                        valor=valor_i, status='PREVISTO',
                        data_vencimento=avancar_data(cd['data_vencimento'], freq, i - 1),
                        observacao=cd.get('observacao') or '',
                        grupo_parcelas=grupo, parcela_num=i, parcela_total=parcelas,
                    )
                messages.success(request, f"'{desc_base}' lançada em {parcelas}x de R$ {base} ({freq_label}) — parcelas previstas em Contas a Pagar.")
            else:
                despesa = form.save()
                messages.success(request, f"Despesa '{despesa.descricao}' — R$ {despesa.valor} — cadastrada.")
            return redirect('despesa_listar')
    else:
        form = DespesaForm()

    return render(request, 'relatorios/despesa_form.html', {
        'form': form,
        'titulo': "Lançar Nova Despesa / Custo"
    })


@login_required
@gestao_required
def fluxo_caixa_projetado(request):
    """Projeção de caixa: saldo de hoje + estimativa de entradas − contas previstas,
    mês a mês, para os próximos meses."""
    from vendas.models import Pedido

    hoje = timezone.localdate()
    meses_a_frente = 6

    # Estimativa de recebimento mensal: média líquida dos últimos 90 dias (ou override)
    override = request.GET.get('receita_mensal', '').replace('.', '').replace(',', '.').strip()
    if override:
        try:
            receita_mensal_estimada = Decimal(override)
        except Exception:
            receita_mensal_estimada = Decimal('0')
    else:
        d90 = hoje - timedelta(days=90)
        r = services.resumo_financeiro(d90, hoje)
        receita_mensal_estimada = (r['entradas_caixa'] / Decimal('3')).quantize(Decimal('0.01'))

    saldo = services.caixa_acumulado()
    linhas = []
    ano, mes = hoje.year, hoje.month
    for i in range(meses_a_frente):
        ini = date(ano, mes, 1)
        fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
        previstas = Despesa.objects.filter(
            status='PREVISTO', data_vencimento__gte=ini, data_vencimento__lte=fim,
        )
        saidas = previstas.aggregate(t=Sum('valor'))['t'] or Decimal('0.00')
        # No mês corrente, só conta o que ainda vai vencer (a partir de hoje)
        entradas = receita_mensal_estimada
        if i == 0:
            saidas = previstas.filter(data_vencimento__gte=hoje).aggregate(t=Sum('valor'))['t'] or Decimal('0.00')
            frac = Decimal(fim.day - hoje.day + 1) / Decimal(fim.day)
            entradas = (receita_mensal_estimada * frac).quantize(Decimal('0.01'))
        saldo_ini = saldo
        saldo = (saldo + entradas - saidas).quantize(Decimal('0.01'))
        linhas.append({
            'mes': f"{MESES_PT[mes]}/{ano}",
            'saldo_inicial': saldo_ini,
            'entradas': entradas,
            'saidas': saidas,
            'saldo_final': saldo,
            'negativo': saldo < 0,
            'contas': list(previstas.order_by('data_vencimento')[:12]),
        })
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

    return render(request, 'relatorios/fluxo_caixa.html', {
        'linhas': linhas,
        'saldo_hoje': services.caixa_acumulado(),
        'receita_mensal_estimada': receita_mensal_estimada,
        'override_ativo': bool(override),
    })


@login_required
@gestao_required
def despesa_editar(request, id):
    despesa = get_object_or_404(Despesa, id=id)
    if request.method == 'POST':
        form = DespesaForm(request.POST, instance=despesa)
        if form.is_valid():
            desp = form.save()

            # Se veio de uma recorrente e o usuário pediu, atualiza a recorrente e regenera as previstas
            if form.cleaned_data.get('alterar_futuros') and desp.despesa_matriz:
                rec = desp.despesa_matriz
                rec.valor_base = desp.valor
                rec.credor = desp.credor
                rec.categoria = desp.categoria
                rec.save()
                propagar_molde_para_previstas(rec, a_partir_de=desp.data_vencimento + timedelta(days=1))
                gerar_despesas_fixas_pendentes(forcar=True)
                messages.info(request, "Despesa recorrente atualizada e contas previstas futuras regeradas com o novo valor.")

            messages.success(request, f"Despesa '{despesa.descricao}' atualizada.")
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
        # Se veio do carrinho de compra: devolve o estoque também
        if despesa.origem == 'ESTOQUE' and despesa.grupo_compra:
            from estoque.services import estornar_compra
            estornar_compra(despesa)  # já apaga a despesa e as movimentações
            messages.success(request, f"Compra '{descricao}' excluída — estoque e despesa desfeitos.")
        else:
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
            n = gerar_despesas_fixas_pendentes(forcar=True)
            messages.success(
                request,
                f"Despesa recorrente cadastrada. {n} conta(s) prevista(s) já em Contas a Pagar. "
                "O sistema cria as próximas sozinho e vai renovando pra sempre — "
                "você nunca precisa recadastrar."
            )
            return redirect('despesa_listar')
    else:
        form = DespesaRecorrenteForm()

    return render(request, 'relatorios/despesa_recorrente_form.html', {
        'form': form,
        'titulo': "Cadastrar Despesa Recorrente"
    })

@login_required
@gestao_required
def despesa_recorrente_editar(request, id):
    rec = get_object_or_404(DespesaRecorrente, id=id)
    if request.method == 'POST':
        form = DespesaRecorrenteForm(request.POST, instance=rec)
        if form.is_valid():
            rec = form.save()
            # Apaga as previstas futuras não vencidas e recria pela regra nova
            apagadas = propagar_molde_para_previstas(rec)
            if rec.ativa:
                n = gerar_despesas_fixas_pendentes(forcar=True)
                messages.info(request, f"{apagadas} conta(s) prevista(s) antiga(s) substituída(s) por {n} nova(s).")
            else:
                messages.info(request, f"Recorrente desativada. {apagadas} conta(s) prevista(s) futura(s) removida(s).")
            messages.success(request, "Despesa recorrente atualizada.")
            return redirect('despesa_listar')
    else:
        form = DespesaRecorrenteForm(instance=rec)

    return render(request, 'relatorios/despesa_recorrente_form.html', {
        'form': form,
        'titulo': f"Editar recorrente: {rec.descricao}"
    })

@login_required
@gestao_required
def despesa_recorrente_excluir(request, id):
    rec = get_object_or_404(DespesaRecorrente, id=id)
    if request.method == 'POST':
        Despesa.objects.filter(despesa_matriz=rec, status='PREVISTO').delete()
        rec.delete()
        messages.success(request, "Despesa recorrente e contas previstas futuras excluídas.")
        return redirect('despesa_listar')

    return render(request, 'relatorios/despesa_recorrente_confirm_delete.html', {'rec': rec, 'molde': rec})

def _rotular_vencimento(despesa, hoje):
    """Anota rótulo/urgência de uma conta prevista para exibição."""
    dias = (despesa.data_vencimento - hoje).days
    if dias < 0:
        despesa.rotulo = f"Atrasada há {abs(dias)} dia{'s' if abs(dias) != 1 else ''}"
        despesa.urgencia = 'atrasada'
    elif dias == 0:
        despesa.rotulo = "Vence hoje"
        despesa.urgencia = 'hoje'
    elif dias <= DIAS_ALERTA_URGENTE:
        despesa.rotulo = f"Vence em {dias} dia{'s' if dias != 1 else ''}"
        despesa.urgencia = 'proxima'
    else:
        despesa.rotulo = f"Vence em {dias} dias"
        despesa.urgencia = 'futura'
    return despesa


def contas_a_pagar_urgentes(hoje=None):
    """Contas previstas atrasadas ou que vencem em até DIAS_ALERTA_URGENTE dias."""
    hoje = hoje or timezone.localdate()
    limite = hoje + timedelta(days=DIAS_ALERTA_URGENTE)
    return Despesa.objects.filter(status='PREVISTO', data_vencimento__lte=limite).order_by('data_vencimento')


@login_required
@gestao_required
def notificacoes_badge(request):
    hoje = timezone.localdate()
    urgentes = list(contas_a_pagar_urgentes(hoje))
    for d in urgentes:
        _rotular_vencimento(d, hoje)
    return render(request, 'relatorios/partials/notificacoes_badge.html', {
        'qtd': len(urgentes),
        'despesas': urgentes[:6],
    })

