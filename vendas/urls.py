from django.urls import path
from . import views

urlpatterns = [
    # Lançamento de Pedidos
    path('novo/', views.pedido_criar, name='pedido_criar'),
    path('painel/', views.pedido_listar, name='pedido_listar'),
    path('pedido/<int:pk>/status/', views.pedido_atualizar_status, name='pedido_atualizar_status'),
    
    # Fechamento Diário de Vendas em Lote
    path('fechamento-diario/', views.fechamento_diario, name='fechamento_diario'),

    # Canais de Venda
    path('canais/', views.canal_listar, name='canal_listar'),
    path('canais/novo/', views.canal_criar, name='canal_criar'),
    path('canais/<int:pk>/editar/', views.canal_editar, name='canal_editar'),
    path('canais/<int:pk>/excluir/', views.canal_excluir, name='canal_excluir'),
]
