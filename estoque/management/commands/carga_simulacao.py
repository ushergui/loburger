"""
Carga inicial para SIMULAÇÃO: define preços de mercado nos insumos e lança uma
abertura de estoque suficiente para vender ~5 unidades de cada lanche (não-combo)
durante 5 dias.

Não gera despesa (é abertura). Zera as movimentações e as vendas anteriores para
a simulação começar limpa.

    python manage.py carga_simulacao
    python manage.py carga_simulacao --lanches-dia 5 --dias 5
"""
import math
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.formats import number_format

from produtos.models import Ingrediente, Produto, PrecoCanal
from estoque.models import MovimentacaoEstoque
from vendas.models import Pedido, EntregaDiaria, ConfiguracaoFinanceira, CanalVenda
from relatorios.models import Despesa


# Preço justo por unidade de COMPRA (R$/kg, R$/l ou R$/un) — referência de mercado
PRECOS_COMPRA = {
    'CARNE ANGUS': '45.00', 'BACON': '32.00',
    'MUSSARELA': '42.00', 'CHEDDAR': '45.00', 'QUEIJO PRATO': '40.00',
    'PROVOLONE': '55.00', 'QUEIJO COALHO': '45.00', 'REQUEIJAO CREMOSO': '22.00',
    'COSTELA DESFIADA': '55.00', 'FAROFA DE BACON': '38.00',
    'TOMATE': '8.00', 'CEBOLA ROXA': '7.00', 'CEBOLA BRANCA': '5.00',
    'CEBOLA CARAMELIZADA': '20.00', 'CEBOLA CRISPY': '48.00',
    'PICKLES': '24.00', 'RUCULA': '28.00', 'PIMENTA JALAPENO': '42.00',
    'GELEIA DE PIMENTA': '38.00', 'BATATA': '13.00',
    'CREME DE AVELA (NUTELLA)': '48.00',
    'MOLHO DA CASA': '16.00', 'MAIONESE VERDE CASEIRA': '18.00',
    'MOLHO BARBECUE': '17.00', 'MOLHO ESPECIAL': '18.00', 'OLEO DE FRITURA': '9.00',
    'PAO TRADICIONAL': '1.80', 'PAO TRADICIONAL COM GERGELIM': '2.00',
    'PAO TRADICIONAL MENOR': '1.40', 'OVO': '0.70', 'ALFACE': '4.00',
    'CATUPIRY EMPANADO': '3.50', 'QUATRO QUEIJOS EMPANADO': '4.20',
    'SOBRECOXA EMPANADA': '4.50', 'FRANGO SUPREMO SEARA': '1.80',
    'MASSA DE CROISSANT': '3.50',
    'REFRIGERANTE LATA 350ML': '3.50', 'REFRIGERANTE PET OU SUCO': '4.00',
    'MIMO INFANTIL': '2.00',
}
FALLBACK_POR_COMPRA = {'g': Decimal('25.00'), 'ml': Decimal('15.00'), 'un': Decimal('2.00'),
                       'kg': Decimal('25.00'), 'l': Decimal('15.00')}

# Custo de aquisição de itens de revenda (produtos comprados prontos)
CUSTO_REVENDA = {
    'coca-cola lata': '3.80', 'coca-cola zero': '3.80', 'fanta': '3.60',
    'guaran': '3.40', 'sprite': '3.60', 'monster': '8.50', 'suco life': '2.80',
    'água mineral com': '2.20', 'agua mineral com': '2.20',
    'água mineral sem': '1.80', 'agua mineral sem': '1.80', 'kitkat': '3.20',
}

BUFFER = Decimal('1.30')  # 30% de folga


def _arredonda_para_cima(valor, unidade):
    passo = 5 if unidade == 'un' else 100
    return Decimal(math.ceil(float(valor) / passo) * passo)


class Command(BaseCommand):
    help = "Carga inicial de simulação: preços nos insumos + abertura de estoque para ~5 lanches/dia por 5 dias."

    def add_arguments(self, parser):
        parser.add_argument('--lanches-dia', type=int, default=5)
        parser.add_argument('--dias', type=int, default=5)

    @transaction.atomic
    def handle(self, *args, **options):
        unidades = options['lanches_dia'] * options['dias']

        # 1. Limpa a base transacional para a simulação começar do zero
        MovimentacaoEstoque.objects.all().delete()
        EntregaDiaria.objects.all().delete()
        Pedido.objects.all().delete()
        Despesa.objects.filter(origem__in=['FECHAMENTO', 'ESTOQUE']).delete()
        cfg = ConfiguracaoFinanceira.get_solo()
        cfg.ultima_geracao_recorrentes = None
        cfg.save(update_fields=['ultima_geracao_recorrentes'])

        # 2. Consumo necessário (só produtos que NÃO são combo)
        necessidade = {}
        produtos = Produto.objects.filter(status=True).exclude(categoria='COMBO')
        for prod in produtos:
            for iid, (ing, qtd) in prod.insumos_consolidados(Decimal(unidades)).items():
                necessidade[iid] = necessidade.get(iid, Decimal('0')) + qtd

        # 3. Preço + abertura de estoque, insumo por insumo
        linhas = []
        for ing in Ingrediente.objects.all():
            fator = ing.obter_fator_conversao
            preco_compra = Decimal(PRECOS_COMPRA.get(
                ing.nome.upper(), FALLBACK_POR_COMPRA.get(ing.unidade_compra, Decimal('20'))))
            ing.custo_unitario = (preco_compra / fator).quantize(Decimal('0.0001'))

            bruto = necessidade.get(ing.id, Decimal('0')) * BUFFER
            if bruto <= 0:
                bruto = Decimal('30') if ing.unidade_medida == 'un' else Decimal('3000')
            qtd = _arredonda_para_cima(bruto, ing.unidade_medida)

            ing.estoque_atual = qtd
            ing.estoque_minimo = _arredonda_para_cima(qtd / Decimal('4'), ing.unidade_medida)
            ing.save()

            MovimentacaoEstoque.objects.create(
                ingrediente=ing, quantidade=qtd, tipo='ABERTURA',
                valor_unitario=ing.custo_unitario,
                observacao="Carga inicial de simulação (não gera despesa).",
            )
            linhas.append((
                ing.nome,
                number_format((qtd / fator).quantize(Decimal('0.001')).normalize(), force_grouping=True),
                ing.unidade_compra,
                number_format(preco_compra.quantize(Decimal('0.01'))),
            ))

        # 4b. Garante preço em todo canal para os produtos não-combo
        def _fator_canal(canal):
            n = canal.nome.lower()
            if 'ifood' in n:
                return Decimal('1.15')
            if 'uai' in n:
                return Decimal('1.08')
            return Decimal('1.00')

        canais = list(CanalVenda.objects.all())
        n_precos = 0
        for prod in Produto.objects.filter(status=True).exclude(categoria='COMBO'):
            existentes = {pc.canal_id: pc.preco for pc in prod.precos_canais.all()}
            # base = preço "de balcão" (canal sem comissão) ou o menor existente, ou CMV x 3
            base = None
            for c in canais:
                if c.taxa_comissao == 0 and c.id in existentes:
                    base = existentes[c.id]
            if base is None and existentes:
                base = min(existentes.values())
            if base is None:
                base = (prod.custo_total * Decimal('3')).quantize(Decimal('1'))
            for c in canais:
                if c.id in existentes:
                    continue
                preco = (base * _fator_canal(c) * 2).quantize(Decimal('1')) / 2  # arredonda p/ R$ 0,50
                PrecoCanal.objects.create(produto=prod, canal=c, preco=preco)
                n_precos += 1

        # 5. Custo de aquisição nas bebidas / revenda
        n_rev = 0
        for prod in Produto.objects.filter(categoria__in=['BEBIDA', 'SOBREMESA']):
            nome = prod.nome.lower()
            for chave, custo in CUSTO_REVENDA.items():
                if chave in nome:
                    prod.custo_aquisicao = Decimal(custo)
                    prod.save(update_fields=['custo_aquisicao'])
                    n_rev += 1
                    break

        # 6. Resumo
        self.stdout.write(self.style.SUCCESS(
            f"\nCarga de simulação pronta: {options['lanches_dia']} lanches/dia x {options['dias']} dias = {unidades} un por lanche.\n"
        ))
        self.stdout.write(f"{'INSUMO':32} {'ABERTURA':>14}   {'CUSTO':>12}")
        self.stdout.write('-' * 62)
        for nome, qtd, un, custo in sorted(linhas):
            self.stdout.write(f"{nome[:32]:32} {qtd:>10} {un:<3}   R$ {custo:>8}/{un}")
        self.stdout.write('-' * 62)
        self.stdout.write(f"{len(linhas)} insumos abastecidos · {n_precos} preços de canal preenchidos · {n_rev} bebidas com custo de aquisição.")
        self.stdout.write(self.style.SUCCESS(
            "Nada de despesa foi gerado (é abertura). Pode ir em Fechamento Diário e simular as vendas."
        ))
