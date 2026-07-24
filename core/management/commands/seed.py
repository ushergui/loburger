import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from core.models import Usuario
from produtos.models import Ingrediente, Produto, FichaTecnicaItem, PrecoCanal
from vendas.models import CanalVenda, Pedido, PedidoItem
from estoque.models import MovimentacaoEstoque

class Command(BaseCommand):
    help = 'Popula o banco de dados do LOL BURGUER com os lanches e ingredientes reais'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Iniciando semeadura de dados reais (Seed)..."))

        # 1. Limpar dados anteriores
        self.stdout.write("Limpando banco de dados...")
        PedidoItem.objects.all().delete()
        Pedido.objects.all().delete()
        MovimentacaoEstoque.objects.all().delete()
        PrecoCanal.objects.all().delete()
        FichaTecnicaItem.objects.all().delete()
        Produto.objects.all().delete()
        Ingrediente.objects.all().delete()
        CanalVenda.objects.all().delete()
        
        # Manter superusuário, mas limpar outros de teste
        get_user_model().objects.exclude(is_superuser=True).delete()

        # 2. Criar Usuários de Teste
        self.stdout.write("Criando usuários de teste...")
        gestor = get_user_model().objects.create_user(
            username='gestor',
            email='gestor@lolburguer.com.br',
            password='lol123password',
            first_name='Yasuo',
            last_name='Gestor',
            role='GESTAO'
        )
        operador = get_user_model().objects.create_user(
            username='caixa',
            email='caixa@lolburguer.com.br',
            password='lol123password',
            first_name='Teemo',
            last_name='Caixa',
            role='OPERADOR'
        )
        self.stdout.write(self.style.SUCCESS("Usuários criados: gestor / caixa (senha: lol123password)"))

        # 3. Criar Canais de Venda
        self.stdout.write("Criando canais de venda...")
        canal_salao = CanalVenda.objects.create(
            nome="Salão / Balcão",
            taxa_comissao=Decimal('0.00'),  # 0%
            taxa_fixa=Decimal('0.00'),
            dias_repasse=0
        )
        canal_ifood = CanalVenda.objects.create(
            nome="iFood Delivery",
            taxa_comissao=Decimal('0.12'),  # 12%
            taxa_fixa=Decimal('1.50'),      # R$ 1.50 por pedido
            dias_repasse=30
        )
        canal_irango = CanalVenda.objects.create(
            nome="UaiRango Delivery",
            taxa_comissao=Decimal('0.08'),  # 8%
            taxa_fixa=Decimal('1.00'),      # R$ 1.00 por pedido
            dias_repasse=15
        )
        self.stdout.write(self.style.SUCCESS("Canais de venda criados: Salão, iFood, UaiRango"))

        # 4. Criar Ingredientes / Insumos
        self.stdout.write("Criando ingredientes/insumos reais...")
        
        # Categorias: PROTEINA, PAO, MOLHO, VEGETAL, QUEIJO, EMBALAGEM, OUTROS
        insumos_data = [
            # Pães
            ('Pão tradicional', 'un', '0.90', 'Padaria Central', 100, 300, 'PAO'),
            ('Pão tradicional (menor)', 'un', '0.75', 'Padaria Central', 50, 150, 'PAO'),
            ('Pão tradicional com gergelim', 'un', '1.00', 'Padaria Central', 50, 200, 'PAO'),
            
            # Carnes
            ('Hambúrguer 170gr', 'un', '3.10', 'Casa de Carnes Angus', 100, 400, 'PROTEINA'),
            ('Hambúrguer 170gr angus', 'un', '3.80', 'Casa de Carnes Angus', 100, 400, 'PROTEINA'),
            ('Hambúrguer smash 90gr angus', 'un', '2.20', 'Casa de Carnes Angus', 100, 300, 'PROTEINA'),
            ('Hambúrguer smash 90gr', 'un', '1.80', 'Casa de Carnes Angus', 100, 300, 'PROTEINA'),
            ('Sobrecoxa empanada', 'un', '2.90', 'Granja Demacia', 40, 150, 'PROTEINA'),
            ('Costela desfiada', 'g', '0.06', 'Casa de Carnes Angus', 1000, 5000, 'PROTEINA'),  # R$ 60 o kg
            
            # Frios / Queijos
            ('Mussarella', 'g', '0.045', 'Freljord Laticínios', 2000, 8000, 'QUEIJO'),  # R$ 45 o kg
            ('Cheddar', 'g', '0.055', 'Freljord Laticínios', 2000, 8000, 'QUEIJO'),     # R$ 55 o kg
            ('Queijo prato', 'g', '0.045', 'Freljord Laticínios', 1000, 4000, 'QUEIJO'),
            ('Queijo provolone', 'g', '0.055', 'Freljord Laticínios', 500, 2000, 'QUEIJO'),
            ('Queijo coalho chapeado', 'un', '2.20', 'Freljord Laticínios', 30, 100, 'QUEIJO'),
            ('Catupiry empanado', 'un', '2.80', 'Zaun Alimentos', 30, 100, 'QUEIJO'),
            ('Quatro queijos empanado', 'un', '3.90', 'Zaun Alimentos', 20, 80, 'QUEIJO'),
            ('Requeijão cremoso', 'g', '0.035', 'Freljord Laticínios', 1000, 3000, 'QUEIJO'),

            # Proteínas secundárias
            ('Bacon', 'g', '0.075', 'Frigorífico Noxus', 1000, 4000, 'PROTEINA'),  # R$ 75 o kg
            ('Ovo', 'un', '0.45', 'Granja Demacia', 60, 200, 'PROTEINA'),

            # Vegetais
            ('Alface', 'g', '0.012', 'Horta Bandópolis', 500, 1500, 'VEGETAL'),
            ('Alface picadinho', 'g', '0.012', 'Horta Bandópolis', 300, 1000, 'VEGETAL'),
            ('Tomate', 'g', '0.010', 'Horta Bandópolis', 500, 2000, 'VEGETAL'),
            ('Cebola roxa', 'g', '0.015', 'Horta Bandópolis', 300, 1200, 'VEGETAL'),
            ('Cebola branca picadinha', 'g', '0.010', 'Horta Bandópolis', 200, 800, 'VEGETAL'),
            ('Cebola caramelizada', 'g', '0.018', 'Horta Bandópolis', 300, 1000, 'VEGETAL'),
            ('Cebola crispy', 'g', '0.025', 'Horta Bandópolis', 200, 800, 'VEGETAL'),
            ('Picles', 'g', '0.022', 'Horta Bandópolis', 200, 800, 'VEGETAL'),
            ('Rúcula', 'g', '0.018', 'Horta Bandópolis', 200, 800, 'VEGETAL'),
            ('Pimenta jalapeño', 'g', '0.028', 'Alquimia Zaun', 100, 500, 'VEGETAL'),

            # Molhos e Geleias
            ('Molho da casa', 'ml', '0.015', 'Zaun Alimentos', 500, 2000, 'MOLHO'),
            ('Maionese verde caseira', 'ml', '0.018', 'Zaun Alimentos', 500, 2000, 'MOLHO'),
            ('Molho barbecue', 'ml', '0.015', 'Zaun Alimentos', 500, 1500, 'MOLHO'),
            ('Geleia de pimenta', 'g', '0.035', 'Zaun Alimentos', 200, 800, 'MOLHO'),
            ('Molho especial', 'ml', '0.018', 'Zaun Alimentos', 500, 2000, 'MOLHO'),
            ('Farofa de Bacon', 'g', '0.045', 'Frigorífico Noxus', 300, 1000, 'PROTEINA'),

            # Outros Insumos
            ('Batata Rústica Congelada', 'g', '0.012', 'Freljord Congelados', 2000, 8000, 'OUTROS'),
            ('Óleo para Fritura', 'ml', '0.008', 'Distribuidora Bilgewater', 1000, 5000, 'OUTROS'),

            # Embalagens e Consumíveis
            ('Caixa LolBurguer Selada', 'un', '0.80', 'Gráfica Piltover', 150, 450, 'EMBALAGEM'),
            ('Sacola de Papel Delivery', 'un', '0.60', 'Gráfica Piltover', 150, 400, 'EMBALAGEM'),
            ('Guardanapo Temático', 'un', '0.05', 'Gráfica Piltover', 1000, 3000, 'EMBALAGEM'),
        ]

        insumos = {}
        for nome, un, custo, fornecedor, estoque_min, estoque_at, cat in insumos_data:
            ing = Ingrediente.objects.create(
                nome=nome,
                unidade_medida=un,
                custo_unitario=Decimal(custo),
                fornecedor=fornecedor,
                estoque_minimo=Decimal(estoque_min),
                estoque_atual=Decimal(estoque_at),
                categoria=cat
            )
            insumos[nome] = ing
            
            # Adiciona movimentação inicial de entrada
            MovimentacaoEstoque.objects.create(
                ingrediente=ing,
                quantidade=Decimal(estoque_at),
                tipo='ENTRADA',
                observacao="Carga inicial de ingredientes reais",
                responsavel=gestor
            )

        self.stdout.write(self.style.SUCCESS(f"Criados {len(insumos)} ingredientes reais no estoque."))

        # 5. Criar Produtos (Cardápio Real do Guilherme)
        self.stdout.write("Criando lanches reais do cardápio...")

        # Lista de lanches e receitas
        # Formato: (nome, categoria, descricao, ingredientes_dict, precos_dict)
        lanches_data = [
            (
                "Draven", "BURGER", 
                "Glorioso e implacável! Pão tradicional, Hambúrguer 170gr angus, mussarella derretida, Bacon crocante, requeijão cremoso, ovo, cebola roxa fatiada, tomate, alface fresca e o molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Mussarella': '30', 'Bacon': '30',
                    'Requeijão cremoso': '30', 'Ovo': '1', 'Cebola roxa': '15', 'Tomate': '20',
                    'Alface': '10', 'Molho da casa': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '38.00', 'iFood': '44.00', 'UaiRango': '41.00'}
            ),
            (
                "Garen", "BURGER",
                "Firme e justiceiro! Pão tradicional, hambúrguer 170gr suculento, cheddar cremoso, cebola caramelizada artesanal, Bacon crocante e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr': '1', 'Cheddar': '30', 'Cebola caramelizada': '20',
                    'Bacon': '30', 'Molho da casa': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '32.00', 'iFood': '38.00', 'UaiRango': '35.00'}
            ),
            (
                "Darius", "BURGER",
                "Força de Noxus! Pão tradicional, hambúrguer 170gr angus, mussarella derretida, picles fatiado, tomate, alface e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Mussarella': '30', 'Picles': '15',
                    'Tomate': '20', 'Alface': '10', 'Molho da casa': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '34.00', 'iFood': '40.00', 'UaiRango': '37.00'}
            ),
            (
                "Briar", "BURGER",
                "Frenesi de sabor! Pão tradicional, hambúrguer smash 90gr angus prensado na chapa, mussarella derretida, ovo frito, cebola roxa, tomate, alface e maionese verde caseira.",
                {
                    'Pão tradicional': '1', 'Hambúrguer smash 90gr angus': '1', 'Mussarella': '30', 'Ovo': '1',
                    'Cebola roxa': '15', 'Tomate': '20', 'Alface': '10', 'Maionese verde caseira': '20',
                    'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '26.00', 'iFood': '31.50', 'UaiRango': '28.50'}
            ),
            (
                "Ekko", "BURGER",
                "Quebra o tempo! Pão tradicional, Catupiry empanado dourante e crocante, ovo, queijo cheddar, cebola roxa, tomate e alface.",
                {
                    'Pão tradicional': '1', 'Catupiry empanado': '1', 'Ovo': '1', 'Cheddar': '30',
                    'Cebola roxa': '15', 'Tomate': '20', 'Alface': '10', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '33.00', 'iFood': '39.00', 'UaiRango': '36.00'}
            ),
            (
                "Rengar", "BURGER",
                "Caçada perfeita! Pão tradicional, hambúrguer 170gr angus, quatro queijos empanado derretendo por dentro, bacon e maionese verde caseira.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Quatro queijos empanado': '1', 'Bacon': '30',
                    'Maionese verde caseira': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '42.00', 'iFood': '49.00', 'UaiRango': '45.50'}
            ),
            (
                "Blitsmah", "BURGER",
                "Puxão de sabor! Pão tradicional, hambúrguer smash 90gr angus, cheddar derretido, cebola caramelizada, Bacon e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer smash 90gr angus': '1', 'Cheddar': '30', 'Cebola caramelizada': '20',
                    'Bacon': '30', 'Molho da casa': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '28.00', 'iFood': '34.00', 'UaiRango': '31.00'}
            ),
            (
                "Blitsmah duplo", "BURGER",
                "Campo estático duplo! Pão tradicional, dois hambúrgueres smash 90gr, duplo cheddar, dupla cebola caramelizada, duplo bacon e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer smash 90gr': '2', 'Cheddar': '60', 'Cebola caramelizada': '40',
                    'Bacon': '60', 'Molho da casa': '30', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '38.00', 'iFood': '45.00', 'UaiRango': '41.50'}
            ),
            (
                "Gnar", "BURGER",
                "Transformação jurássica! Pão tradicional, Hambúrguer 170gr angus, queijo mussarella derretido (ou queijo à sua escolha) e maionese verde caseira.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Mussarella': '30',
                    'Maionese verde caseira': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '31.00', 'iFood': '36.50', 'UaiRango': '33.50'}
            ),
            (
                "Lux", "BURGER",
                "Centelha final de leveza! Pão tradicional (menor), hambúrguer smash 90gr angus, queijo cheddar derretido (ou queijo à sua escolha).",
                {
                    'Pão tradicional (menor)': '1', 'Hambúrguer smash 90gr angus': '1', 'Cheddar': '30',
                    'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '22.00', 'iFood': '26.50', 'UaiRango': '24.00'}
            ),
            (
                "Sett", "BURGER",
                "O Chefe! Pão tradicional (menor) selado e queijo quente derretido à sua escolha (mussarella padrão, cheddar ou queijo prato).",
                {
                    'Pão tradicional (menor)': '1', 'Mussarella': '30',
                    'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '16.00', 'iFood': '20.00', 'UaiRango': '18.00'}
            ),
            (
                "Jhin", "BURGER",
                "O quarto disparo perfeito! Pão tradicional com gergelim, sobrecoxa empanada crocante, cebola roxa, tomate, alface e molho barbecue.",
                {
                    'Pão tradicional com gergelim': '1', 'Sobrecoxa empanada': '1', 'Cebola roxa': '15',
                    'Tomate': '20', 'Alface': '10', 'Molho barbecue': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '29.00', 'iFood': '35.00', 'UaiRango': '32.00'}
            ),
            (
                "GangPlank", "BURGER",
                "Barril de pólvora! Pão tradicional, hambúrguer 170gr angus, queijo cheddar, requeijão cremoso, farofa de bacon crocante e cebola crispy.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Cheddar': '30', 'Requeijão cremoso': '30',
                    'Farofa de Bacon': '20', 'Cebola crispy': '15', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '39.00', 'iFood': '46.00', 'UaiRango': '42.50'}
            ),
            (
                "Yasuo", "BURGER",
                "Tempestade de aço! Pão tradicional, triplo hambúrguer smash 90gr, triplo cheddar derretido, cebola roxa fatiada, bacon crocante e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer smash 90gr': '3', 'Cheddar': '90', 'Cebola roxa': '15',
                    'Bacon': '40', 'Molho da casa': '30', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '44.00', 'iFood': '52.00', 'UaiRango': '48.00'}
            ),
            (
                "Xin zhao", "BURGER",
                "Determinação de ferro! Pão tradicional, duplo hambúrguer 170gr angus, mussarella, cheddar, bacon crocante, maionese verde caseira e molho da casa.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '2', 'Mussarella': '30', 'Cheddar': '30',
                    'Bacon': '40', 'Maionese verde caseira': '20', 'Molho da casa': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '46.00', 'iFood': '54.00', 'UaiRango': '50.00'}
            ),
            (
                "Jax", "BURGER",
                "O Grão-Mestre das Armas! Sem pão, servido diretamente no prato com hambúrguer 170gr angus, requeijão cremoso farto, costela desfiada temperada e cebola crispy.",
                {
                    'Hambúrguer 170gr angus': '1', 'Requeijão cremoso': '30', 'Costela desfiada': '40',
                    'Cebola crispy': '15', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '38.00', 'iFood': '45.00', 'UaiRango': '41.50'}
            ),
            (
                "Barão Nashor", "BURGER",
                "Monstro épico! Pão tradicional, duplo hambúrguer 170gr angus, Catupiry empanado, bacon crocante e maionese verde caseira.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '2', 'Catupiry empanado': '1', 'Bacon': '40',
                    'Maionese verde caseira': '30', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '3'
                },
                {'Salão': '49.00', 'iFood': '57.00', 'UaiRango': '53.00'}
            ),
            (
                "Kennen", "BURGER",
                "Surto elétrico de rúcula! Pão tradicional, hambúrguer 170gr, queijo prato derretido, cebola roxa, tomate, rúcula fresca e maionese verde caseira.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr': '1', 'Queijo prato': '30', 'Cebola roxa': '15',
                    'Tomate': '20', 'Rúcula': '15', 'Maionese verde caseira': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '31.00', 'iFood': '37.00', 'UaiRango': '34.00'}
            ),
            (
                "Brand", "BURGER",
                "Explosão piroclástica picante! Pão tradicional, hambúrguer 170gr angus, queijo coalho chapeado na grelha, pimenta jalapeño, rúcula fresca e geleia de pimenta defumada.",
                {
                    'Pão tradicional': '1', 'Hambúrguer 170gr angus': '1', 'Queijo coalho chapeado': '1', 'Pimenta jalapeño': '15',
                    'Rúcula': '15', 'Geleia de pimenta': '20', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '39.00', 'iFood': '46.00', 'UaiRango': '42.50'}
            ),
            (
                "Pyke", "BURGER",
                "Morte das profundezas! Pão tradicional com gergelim, duplo hambúrguer smash 90gr, duplo cheddar derretido, duplo alface picadinho, cebola branca picadinha, picles fatiado e molho especial Hextech.",
                {
                    'Pão tradicional com gergelim': '1', 'Hambúrguer smash 90gr': '2', 'Cheddar': '60',
                    'Alface picadinho': '20', 'Cebola branca picadinha': '15', 'Picles': '15',
                    'Molho especial': '30', 'Caixa LolBurguer Selada': '1', 'Guardanapo Temático': '2'
                },
                {'Salão': '35.00', 'iFood': '41.50', 'UaiRango': '38.00'}
            )
        ]

        produtos_lista = []
        for nome, cat, desc, ing_dict, precos_dict in lanches_data:
            prod = Produto.objects.create(
                nome=nome,
                categoria=cat,
                descricao=desc,
                status=True
            )
            produtos_lista.append(prod)

            # Criar Ficha Técnica para o produto
            for ing_nome, qtd_str in ing_dict.items():
                FichaTecnicaItem.objects.create(
                    produto=prod,
                    ingrediente=insumos[ing_nome],
                    quantidade=Decimal(qtd_str)
                )

            # Criar Preços por Canal
            PrecoCanal.objects.create(produto=prod, canal=canal_salao, preco=Decimal(precos_dict['Salão']))
            PrecoCanal.objects.create(produto=prod, canal=canal_ifood, preco=Decimal(precos_dict['iFood']))
            PrecoCanal.objects.create(produto=prod, canal=canal_irango, preco=Decimal(precos_dict['UaiRango']))

        # Adicionar Batatas e Poções padrão para manter variedade de categorias
        batatas = Produto.objects.create(
            nome="Batatas de Summoners Rift",
            categoria="ACOMPANHAMENTO",
            descricao="Batatas rústicas crocantes fritas com páprica Hextech.",
            status=True
        )
        FichaTecnicaItem.objects.create(produto=batatas, ingrediente=insumos['Batata Rústica Congelada'], quantidade=Decimal('200.000'))
        FichaTecnicaItem.objects.create(produto=batatas, ingrediente=insumos['Óleo para Fritura'], quantidade=Decimal('30.000'))
        FichaTecnicaItem.objects.create(produto=batatas, ingrediente=insumos['Guardanapo Temático'], quantidade=Decimal('2.000'))
        PrecoCanal.objects.create(produto=batatas, canal=canal_salao, preco=Decimal('16.00'))
        PrecoCanal.objects.create(produto=batatas, canal=canal_ifood, preco=Decimal('20.00'))
        PrecoCanal.objects.create(produto=batatas, canal=canal_irango, preco=Decimal('18.00'))
        produtos_lista.append(batatas)

        pot_vida = Produto.objects.create(
            nome="Poção de Vida Rubra",
            categoria="BEBIDA",
            descricao="Suco natural de morango e amora bem gelado.",
            status=True
        )
        FichaTecnicaItem.objects.create(produto=pot_vida, ingrediente=insumos['Guardanapo Temático'], quantidade=Decimal('1.000'))
        PrecoCanal.objects.create(produto=pot_vida, canal=canal_salao, preco=Decimal('10.00'))
        PrecoCanal.objects.create(produto=pot_vida, canal=canal_ifood, preco=Decimal('12.50'))
        PrecoCanal.objects.create(produto=pot_vida, canal=canal_irango, preco=Decimal('11.00'))
        produtos_lista.append(pot_vida)

        pot_mana = Produto.objects.create(
            nome="Poção de Mana Azul",
            categoria="BEBIDA",
            descricao="Soda refrescante italiana de Blue Curaçao com capim limão.",
            status=True
        )
        FichaTecnicaItem.objects.create(produto=pot_mana, ingrediente=insumos['Guardanapo Temático'], quantidade=Decimal('1.000'))
        PrecoCanal.objects.create(produto=pot_mana, canal=canal_salao, preco=Decimal('10.00'))
        PrecoCanal.objects.create(produto=pot_mana, canal=canal_ifood, preco=Decimal('12.50'))
        PrecoCanal.objects.create(produto=pot_mana, canal=canal_irango, preco=Decimal('11.00'))
        produtos_lista.append(pot_mana)

        self.stdout.write(self.style.SUCCESS(f"Tabela de preços por canal gerada para os {len(produtos_lista)} lanches e adicionais."))

        # 6. Gerar Histórico de Vendas Retroativas (Últimos 30 dias)
        self.stdout.write("Gerando histórico de vendas retroativas...")
        
        canais = [canal_salao, canal_ifood, canal_irango]
        vendas_count = 0
        total_dias = 30
        agora = timezone.now()

        for dia_atras in range(total_dias, -1, -1):
            data_venda = agora - timedelta(days=dia_atras)
            pedidos_no_dia = random.randint(1, 6)
            
            for _ in range(pedidos_no_dia):
                canal = random.choice(canais)
                status = random.choices(['RECEBIDO', 'PREPARO', 'CONCLUIDO', 'CANCELADO'], weights=[2, 2, 90, 6], k=1)[0]
                
                # Cria o Pedido com data forçada
                pedido = Pedido.objects.create(
                    cliente_nome=f"Invocador {random.randint(100, 999)}",
                    canal=canal,
                    status=status,
                    estoque_baixado=False
                )
                
                # Adiciona de 1 a 3 itens ao pedido
                num_itens = random.randint(1, 3)
                itens_adicionados = set()
                
                for _ in range(num_itens):
                    prod = random.choice(produtos_lista)
                    if prod.id in itens_adicionados:
                        continue
                    itens_adicionados.add(prod.id)
                    
                    preco_canal_obj = PrecoCanal.objects.get(produto=prod, canal=canal)
                    qty = random.randint(1, 2)
                    
                    PedidoItem.objects.create(
                        pedido=pedido,
                        produto=prod,
                        quantidade=qty,
                        preco_unitario=preco_canal_obj.preco
                    )

                # Força a data de criação correta (usando update)
                data_pedido_especifica = data_venda.replace(
                    hour=random.randint(18, 23),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59)
                )
                
                Pedido.objects.filter(id=pedido.id).update(data_criacao=data_pedido_especifica)
                
                pedido_atualizado = Pedido.objects.get(id=pedido.id)
                pedido_atualizado.recalcular_valores_financeiros(save=True)
                
                # Se o status for concluído, desconta estoque
                if status == 'CONCLUIDO':
                    pedido_atualizado.processar_baixa_estoque(responsavel=gestor)
                
                vendas_count += 1

        self.stdout.write(self.style.SUCCESS(f"Semeadura de dados finalizada! {vendas_count} pedidos gerados."))
