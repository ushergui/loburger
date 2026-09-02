"""
Cadastra os ADICIONAIS (extras que o cliente adiciona ao lanche): pães,
ingredientes avulsos e molhos. Cada adicional vira um Produto (categoria
ADICIONAL) com ficha técnica de 1 insumo, para dar baixa de estoque quando
vendido.

Preços: a lista abaixo é o preço no APP PRÓPRIO (aplicativo online, comissão 0).
Para iFood e UaiRango aplica-se a MESMA proporção do lanche "Barão Nashor"
(preço do canal ÷ preço do app próprio), arredondando para R$ 0,10.

Idempotente: pode rodar de novo que ele só atualiza.

    python manage.py carga_adicionais
"""
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from produtos.models import Produto, Ingrediente, FichaTecnicaItem, PrecoCanal
from vendas.models import CanalVenda


# Insumos que talvez ainda não existam (nome, un_consumo, un_compra, categoria, custo_unitario)
NOVOS_INGREDIENTES = [
    ('PAO AUSTRALIANO', 'un', 'un', 'PAO', '2.20'),
    ('PAO BRIOCHE', 'un', 'un', 'PAO', '2.20'),
    ('MAIONESE DE BACON', 'ml', 'l', 'MOLHO', '0.022'),
    ('MAIONESE DEFUMADA', 'ml', 'l', 'MOLHO', '0.020'),
    ('MOLHO DE CHEDDAR', 'ml', 'l', 'MOLHO', '0.035'),
]

# nome do adicional (rótulo do app)  ->  (preço app próprio, insumo, qtd no consumo)
ADICIONAIS = {
    # --- Pães (troca de pão; tradicionais não têm custo extra p/ o cliente) ---
    'Pão Australiano':                 ('2.00', 'PAO AUSTRALIANO', 1),
    'Pão Brioche':                     ('2.00', 'PAO BRIOCHE', 1),
    'Pão Tradicional':                 ('0.00', 'PAO TRADICIONAL', 1),
    'Pão Tradicional com Gergelim':    ('0.00', 'PAO TRADICIONAL COM GERGELIM', 1),

    # --- Ingredientes avulsos ---
    '4 Queijo Empanado':              ('13.00', 'QUATRO QUEIJOS EMPANADO', 2),
    'Alface':                         ('1.00', 'ALFACE', Decimal('0.1')),
    'Bacon':                          ('4.50', 'BACON', 40),
    'Catupiry Empanado':             ('13.00', 'CATUPIRY EMPANADO', 2),
    'Cebola Caramelizada':            ('3.50', 'CEBOLA CARAMELIZADA', 40),
    'Cebola Crispy':                  ('3.50', 'CEBOLA CRISPY', 25),
    'Cebola Roxa Crua':              ('3.00', 'CEBOLA ROXA', 30),
    'Cheddar':                        ('4.50', 'CHEDDAR', 35),
    'Costela Desfiada':             ('10.00', 'COSTELA DESFIADA', 60),
    'Farofa de Bacon':               ('4.50', 'FAROFA DE BACON', 40),
    'Hambúrguer Angus 170g':        ('12.00', 'CARNE ANGUS', 170),
    'Hambúrguer Angus 90g':          ('8.00', 'CARNE ANGUS', 90),
    'Muçarela':                       ('4.50', 'MUSSARELA', 35),
    'Ovo':                            ('2.00', 'OVO', 1),
    'Picles':                         ('3.50', 'PICKLES', 30),
    'Queijo Coalho':                  ('7.00', 'QUEIJO COALHO', 50),
    'Queijo Prato':                   ('4.50', 'QUEIJO PRATO', 35),
    'Queijo Provolone':               ('5.50', 'PROVOLONE', 35),
    'Requeijão Cremoso':              ('4.50', 'REQUEIJAO CREMOSO', 30),
    'Rúcula':                         ('2.50', 'RUCULA', 15),
    'Sobrecoxa Empanada':          ('10.00', 'SOBRECOXA EMPANADA', 1),
    'Tomate':                         ('1.00', 'TOMATE', 30),
    'Geleia de Pimenta':             ('2.50', 'GELEIA DE PIMENTA', 25),
    'Pimenta Jalapeño':              ('2.00', 'PIMENTA JALAPENO', 20),

    # --- Molhos adicionais ---
    'Maionese de Bacon':             ('3.50', 'MAIONESE DE BACON', 40),
    'Maionese Defumada':             ('3.50', 'MAIONESE DEFUMADA', 40),
    'Maionese Verde':                ('3.50', 'MAIONESE VERDE CASEIRA', 40),
    'Molho Barbecue':                ('3.50', 'MOLHO BARBECUE', 40),
    'Molho da Casa':                 ('3.50', 'MOLHO DA CASA', 40),
    'Molho de Cheddar Pote 100ml':  ('12.00', 'MOLHO DE CHEDDAR', 100),
    'Molho de Cheddar Pote 50ml':    ('6.00', 'MOLHO DE CHEDDAR', 50),
}

CENTAVO_10 = Decimal('0.10')


def _arredonda_10(valor):
    return (valor / CENTAVO_10).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * CENTAVO_10


class Command(BaseCommand):
    help = "Cadastra os adicionais (pães, ingredientes e molhos) como produtos vendáveis."

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Insumos que faltam
        for nome, un, compra, cat, custo in NOVOS_INGREDIENTES:
            ing, criado = Ingrediente.objects.get_or_create(
                nome=nome,
                defaults=dict(unidade_medida=un, unidade_compra=compra, categoria=cat,
                              custo_unitario=Decimal(custo),
                              estoque_atual=Decimal('0'), estoque_minimo=Decimal('0')),
            )
            if criado:
                self.stdout.write(self.style.SUCCESS(f"+ insumo: {nome} (R$ {custo}/{un})"))

        ing_por_nome = {i.nome.upper(): i for i in Ingrediente.objects.all()}

        # 2. Proporção do Barão Nashor entre os canais
        canais = list(CanalVenda.objects.all())
        canal_base = next((c for c in canais if c.taxa_comissao == 0), None)
        if canal_base is None:
            canal_base = min(canais, key=lambda c: c.taxa_comissao)

        barao = Produto.objects.filter(nome__icontains='bar', categoria='BURGER').first()
        precos_barao = {}
        if barao:
            precos_barao = {pc.canal_id: pc.preco for pc in barao.precos_canais.all()}
        base_barao = precos_barao.get(canal_base.id)

        proporcao = {}
        for c in canais:
            if c.id == canal_base.id or not base_barao:
                proporcao[c.id] = Decimal('1.00')
            elif precos_barao.get(c.id):
                proporcao[c.id] = (precos_barao[c.id] / base_barao)
            else:
                # sem referência: usa a proporção "de mercado" (comissão a mais)
                proporcao[c.id] = (Decimal('1') + c.taxa_online) / (Decimal('1') + canal_base.taxa_online)

        self.stdout.write("\nProporção aplicada (base = %s):" % canal_base.nome)
        for c in canais:
            self.stdout.write(f"  {c.nome:22} x {proporcao[c.id].quantize(Decimal('0.0001'))}")

        # 3. Cria/atualiza cada adicional
        self.stdout.write("\n== ADICIONAIS ==")
        criados = atualizados = 0
        for rotulo, (preco_app, ing_nome, qtd) in ADICIONAIS.items():
            ing = ing_por_nome.get(ing_nome.upper())
            if not ing:
                raise SystemExit(f"Insumo não encontrado: {ing_nome!r}")

            prod, criado = Produto.objects.get_or_create(
                nome=rotulo,
                defaults=dict(categoria='ADICIONAL', status=True,
                              descricao=f"Adicional: {ing.nome.title()}."),
            )
            if not criado:
                prod.categoria = 'ADICIONAL'
                prod.status = True
                prod.save(update_fields=['categoria', 'status'])
            criados += criado
            atualizados += not criado

            # ficha: 1 insumo
            prod.ficha_tecnica.all().delete()
            FichaTecnicaItem.objects.create(
                produto=prod, ingrediente=ing, quantidade=Decimal(str(qtd)))

            # preços por canal
            preco_app = Decimal(preco_app)
            for c in canais:
                if preco_app == 0:
                    preco = Decimal('0.00')
                elif c.id == canal_base.id:
                    preco = preco_app
                else:
                    preco = _arredonda_10(preco_app * proporcao[c.id])
                PrecoCanal.objects.update_or_create(
                    produto=prod, canal=c, defaults={'preco': preco})

            precos_txt = " | ".join(
                f"{c.nome.split()[0]} R$ {PrecoCanal.objects.get(produto=prod, canal=c).preco}"
                for c in canais)
            self.stdout.write(
                f"  {rotulo[:30]:30} CMV R$ {prod.custo_total:>6}   {precos_txt}")

        self.stdout.write(self.style.SUCCESS(
            f"\n{criados} adicionais criados, {atualizados} atualizados. "
            f"Categoria 'Adicionais' no Cardápio."))
