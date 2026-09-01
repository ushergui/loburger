from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_redirect, name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.logout_usuario, name='logout'),
    path('tutorial/', views.tutorial_view, name='tutorial'),
    path('auditoria/', views.auditoria_listar, name='auditoria_listar'),

    path('usuarios/', views.usuario_listar, name='usuario_listar'),
    path('usuarios/novo/', views.usuario_criar, name='usuario_criar'),
    path('usuarios/<int:pk>/editar/', views.usuario_editar, name='usuario_editar'),
    path('usuarios/<int:pk>/senha/', views.usuario_resetar_senha, name='usuario_resetar_senha'),
    path('usuarios/<int:pk>/excluir/', views.usuario_excluir, name='usuario_excluir'),
]
