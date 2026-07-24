from django.urls import path
from . import views

urlpatterns = [
    # Ingredientes
    path('ingredientes/', views.ingrediente_listar, name='ingrediente_listar'),
    path('ingredientes/novo/', views.ingrediente_criar, name='ingrediente_criar'),
    path('ingredientes/<int:pk>/editar/', views.ingrediente_editar, name='ingrediente_editar'),
    path('ingredientes/<int:pk>/excluir/', views.ingrediente_excluir, name='ingrediente_excluir'),
    
    # Produtos (Cardápio)
    path('itens/', views.produto_listar, name='produto_listar'),
    path('itens/novo/', views.produto_criar, name='produto_criar'),
    path('itens/<int:pk>/editar/', views.produto_editar, name='produto_editar'),
    path('itens/<int:pk>/excluir/', views.produto_excluir, name='produto_excluir'),
    
    # Ficha Técnica e Preços
    path('itens/<int:pk>/ficha-tecnica/', views.ficha_tecnica_montar, name='ficha_tecnica_montar'),
    path('itens/<int:produto_pk>/ficha-tecnica/remover/<int:item_pk>/', views.ficha_tecnica_remover_ingrediente, name='ficha_tecnica_remover_ingrediente'),
    path('itens/<int:pk>/precos-parcial/', views.produto_precos_parcial, name='produto_precos_parcial'),
]
