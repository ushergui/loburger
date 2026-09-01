from django.urls import path
from .views import CustomLoginView, logout_usuario, home_redirect, tutorial_view, auditoria_listar

urlpatterns = [
    path('', home_redirect, name='home'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', logout_usuario, name='logout'),
    path('tutorial/', tutorial_view, name='tutorial'),
    path('auditoria/', auditoria_listar, name='auditoria_listar'),
]
