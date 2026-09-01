"""
Monta as fichas técnicas dos lanches com quantidades, tendo o Barão Nashor
como referência de escala (carne 170 g por hambúrguer, bacon 25 g por porção,
molho 30 ml, pão / empanados 1 un).

Reconstrói do zero a ficha de cada produto listado aqui. Não toca em produto
que não estiver no dicionário.

    python manage.py montar_fichas_tecnicas
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from produtos.models import Produto, Ingrediente, FichaTecnicaItem


# Ingredientes que talvez ainda não existam no catálogo (nome, un_consumo, un_compra, categoria)
NOVOS_INGREDIENTES = [
    ('OLEO DE FRITURA', 'ml', 'l', 'OUTROS'),
    ('MASSA DE CROISSANT', 'un', 'un', 'OUTROS'),
    ('CREME DE AVELA (NUTELLA)', 'g', 'kg', 'OUTROS'),
    ('FRANGO SUPREMO SEARA', 'un', 'un', 'PROTEINA'),
    ('REFRIGERANTE LATA 350ML', 'un', 'un', 'OUTROS'),
    ('REFRIGERANTE PET OU SUCO', 'un', 'un', 'OUTROS'),
    ('MIMO INFANTIL', 'un', 'un', 'OUTROS'),
]

# ---------------------------------------------------------------------------
# HAMBÚRGUERES  — nome no banco -> {ingrediente: quantidade na unidade de consumo}
# Fatia de queijo = 35 g (Duplo = 70 g, "4 fatias" = 140 g, "6 fatias" = 210 g)
# Alface: 0,1 un (um pé rende ~10 lanches)
# ---------------------------------------------------------------------------
BURGERS = {
    'BRAND': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'QUEIJO COALHO': 60,
        'GELEIA DE PIMENTA': 20, 'RUCULA': 15, 'PIMENTA JALAPENO': 10,
    },
    'BLITSMAH': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 90, 'CHEDDAR': 70, 'BACON': 25,
        'CEBOLA CARAMELIZADA': 20, 'MOLHO DA CASA': 30,
    },
    'BLITSMAH DUPLO': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 180, 'CHEDDAR': 70, 'BACON': 50,
        'CEBOLA CARAMELIZADA': 40, 'MOLHO DA CASA': 30,
    },
    'BRIAR': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 90, 'MUSSARELA': 35, 'OVO': 1,
        'CEBOLA ROXA': 20, 'TOMATE': 20, 'ALFACE': Decimal('0.1'), 'MAIONESE VERDE CASEIRA': 30,
    },
    'DARIUS': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'MUSSARELA': 35, 'PICKLES': 15,
        'TOMATE': 20, 'ALFACE': Decimal('0.1'), 'MOLHO DA CASA': 30,
    },
    'DRAVEN': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'MUSSARELA': 35, 'BACON': 25, 'OVO': 1,
        'CEBOLA ROXA': 20, 'REQUEIJAO CREMOSO': 25, 'TOMATE': 20, 'ALFACE': Decimal('0.1'),
        'MOLHO DA CASA': 30,
    },
    'EKKO': {
        'PAO TRADICIONAL': 1, 'CATUPIRY EMPANADO': 1, 'CHEDDAR': 35, 'OVO': 1,
        'CEBOLA ROXA': 20, 'ALFACE': Decimal('0.1'), 'TOMATE': 20,
    },
    'GANGPLANK': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'CHEDDAR': 35, 'FAROFA DE BACON': 15,
        'REQUEIJAO CREMOSO': 25, 'CEBOLA CRISPY': 15,
    },
    'GAREN': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'CHEDDAR': 70, 'BACON': 25,
        'CEBOLA CARAMELIZADA': 20, 'MOLHO DA CASA': 30,
    },
    'GNAR': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'MUSSARELA': 35, 'MAIONESE VERDE CASEIRA': 30,
    },
    'JAX': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'REQUEIJAO CREMOSO': 25,
        'COSTELA DESFIADA': 70, 'CEBOLA CRISPY': 15,
    },
    'JHIN': {
        'PAO TRADICIONAL': 1, 'SOBRECOXA EMPANADA': 1, 'CEBOLA ROXA': 20,
        'MOLHO BARBECUE': 30, 'ALFACE': Decimal('0.1'), 'TOMATE': 20,
    },
    'KENNEN': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'QUEIJO PRATO': 35, 'CEBOLA ROXA': 20,
        'TOMATE': 20, 'RUCULA': 15, 'MAIONESE VERDE CASEIRA': 30,
    },
    'PYKE': {
        'PAO TRADICIONAL COM GERGELIM': 1, 'CARNE ANGUS': 180, 'CHEDDAR': 140,
        'CEBOLA BRANCA': 15, 'PICKLES': 15, 'ALFACE': Decimal('0.1'), 'MOLHO DA CASA': 30,
    },
    'RENGAR': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 170, 'QUATRO QUEIJOS EMPANADO': 1,
        'BACON': 25, 'PICKLES': 15, 'MAIONESE VERDE CASEIRA': 30,
    },
    'XIN ZHAO': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 340, 'MUSSARELA': 35, 'CHEDDAR': 35,
        'BACON': 25, 'MAIONESE VERDE CASEIRA': 30, 'MOLHO DA CASA': 30,
    },
    'YASUO': {
        'PAO TRADICIONAL': 1, 'CARNE ANGUS': 270, 'CHEDDAR': 210, 'CEBOLA ROXA': 20,
        'BACON': 25, 'MOLHO DA CASA': 30,
    },
    # Lux e Sett: montados pela descrição do produto (não vieram na lista de ingredientes)
    'LUX': {
        'PAO TRADICIONAL MENOR': 1, 'CARNE ANGUS': 90, 'MUSSARELA': 35,
    },
    'SETT': {
        'PAO TRADICIONAL MENOR': 1, 'MUSSARELA': 70,
    },
}

# ---------------------------------------------------------------------------
# ACOMPANHAMENTOS / CROISSANTS / ENTRADA  — quantidades estimadas (revisar)
# ---------------------------------------------------------------------------
OUTROS_PRODUTOS = {
    'Batata Frita Pequena': {'BATATA': 120, 'OLEO DE FRITURA': 8},
    'Batata Frita Grande': {'BATATA': 200, 'OLEO DE FRITURA': 12},
    'Batata Frita Pequena c/ Cheddar e Bacon': {'BATATA': 120, 'OLEO DE FRITURA': 8, 'CHEDDAR': 40, 'BACON': 30},
    'Batata Frita Grande c/ Cheddar e Bacon': {'BATATA': 200, 'OLEO DE FRITURA': 12, 'CHEDDAR': 50, 'BACON': 40},
    'Batata Frita Pequena c/ Catupiry e Bacon': {'BATATA': 120, 'OLEO DE FRITURA': 8, 'REQUEIJAO CREMOSO': 40, 'BACON': 30},
    'Batata Frita Grande c/ Catupiry e Bacon': {'BATATA': 200, 'OLEO DE FRITURA': 12, 'REQUEIJAO CREMOSO': 50, 'BACON': 40},
    'Croissant de Costela, Mussarela e Bacon': {'MASSA DE CROISSANT': 1, 'COSTELA DESFIADA': 80, 'MUSSARELA': 40, 'BACON': 25, 'MOLHO DA CASA': 20},
    'Croissant de Nutella': {'MASSA DE CROISSANT': 1, 'CREME DE AVELA (NUTELLA)': 50},
    'Chicken Supremo Seara (8 un + Molho)': {'FRANGO SUPREMO SEARA': 8, 'MOLHO DA CASA': 40},
}

# ---------------------------------------------------------------------------
# COMBOS  — lanche + batata + bebida (expansão dos ingredientes)
# ---------------------------------------------------------------------------
# Combos como composição de PRODUTOS + ingredientes extras.
#   'produtos': {nome_do_produto: qtd}   ·   'ingredientes': {nome_do_ingrediente: qtd}
COMBOS = {
    'Combo Demacia (Garen + Fritas + Refri)': {
        'produtos': {'GAREN': 1, 'Batata Frita Grande': 1},
        'ingredientes': {'REFRIGERANTE LATA 350ML': 1},
    },
    'Combo Ionia (Kennen + Fritas + Refri)': {
        'produtos': {'KENNEN': 1, 'Batata Frita Grande': 1},
        'ingredientes': {'REFRIGERANTE LATA 350ML': 1},
    },
    'Combo Infantil (Lux ou Sett + Refri/Suco + Mimo)': {
        'produtos': {'LUX': 1, 'Batata Frita Pequena': 1},
        'ingredientes': {'REFRIGERANTE PET OU SUCO': 1, 'MIMO INFANTIL': 1},
    },
}


class Command(BaseCommand):
    help = "Monta as fichas técnicas dos lanches com quantidades (referência: Barão Nashor)."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Garante os ingredientes novos
        for nome, un, compra, cat in NOVOS_INGREDIENTES:
            _, criado = Ingrediente.objects.get_or_create(
                nome=nome,
                defaults=dict(unidade_medida=un, unidade_compra=compra, categoria=cat,
                              custo_unitario=Decimal('0'), estoque_atual=Decimal('0'),
                              estoque_minimo=Decimal('0')),
            )
            if criado:
                self.stdout.write(self.style.SUCCESS(f"+ ingrediente: {nome}"))

        ing_por_nome = {i.nome.upper(): i for i in Ingrediente.objects.all()}

        def resolve(nome):
            ing = ing_por_nome.get(nome.upper())
            if not ing:
                raise SystemExit(f"Ingrediente não encontrado no catálogo: {nome!r}")
            return ing

        def aplicar(produto, receita):
            produto.ficha_tecnica.all().delete()
            total = Decimal('0.00')
            for nome_ing, qtd in receita.items():
                ing = resolve(nome_ing)
                q = Decimal(str(qtd))
                FichaTecnicaItem.objects.create(produto=produto, ingrediente=ing, quantidade=q)
                total += (q * ing.custo_unitario)
            return total.quantize(Decimal('0.01'))

        def get_produto(nome):
            p = Produto.objects.filter(nome__iexact=nome).first()
            if not p:
                self.stdout.write(self.style.WARNING(f"  (produto não existe, pulado): {nome}"))
            return p

        # 2. Hambúrgueres
        self.stdout.write("\n== HAMBÚRGUERES ==")
        for nome, receita in BURGERS.items():
            p = get_produto(nome)
            if not p:
                continue
            custo = aplicar(p, receita)
            self.stdout.write(f"  {p.nome:16} {len(receita)} itens  ~ CMV R$ {custo}")

        # 3. Acompanhamentos / croissants / entrada
        self.stdout.write("\n== ACOMPANHAMENTOS / CROISSANTS / ENTRADA ==")
        for nome, receita in OUTROS_PRODUTOS.items():
            p = get_produto(nome)
            if not p:
                continue
            custo = aplicar(p, receita)
            self.stdout.write(f"  {p.nome[:38]:38} ~ CMV R$ {custo}")

        # 4. Combos = produtos componentes + ingredientes extras
        self.stdout.write("\n== COMBOS (lanche + batata como PRODUTOS + bebida) ==")
        for nome, comp in COMBOS.items():
            p = get_produto(nome)
            if not p:
                continue
            p.ficha_tecnica.all().delete()
            for prod_nome, qtd in comp.get('produtos', {}).items():
                sub = Produto.objects.filter(nome__iexact=prod_nome).first()
                if sub:
                    FichaTecnicaItem.objects.create(produto=p, produto_componente=sub, quantidade=Decimal(str(qtd)))
            for ing_nome, qtd in comp.get('ingredientes', {}).items():
                FichaTecnicaItem.objects.create(produto=p, ingrediente=resolve(ing_nome), quantidade=Decimal(str(qtd)))
            self.stdout.write(f"  {p.nome[:44]:44} ~ CMV R$ {p.custo_total}")

        self.stdout.write(self.style.SUCCESS("\nFichas montadas. Revise as quantidades pela tela do Cardápio."))
