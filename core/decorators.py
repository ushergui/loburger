from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

def gestao_required(view_func):
    # Decorator para views baseadas em função que exige nível GESTAO
    def _wrapped_view_func(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == 'GESTAO':
            return view_func(request, *args, **kwargs)
        messages.error(request, "Acesso negado: Apenas a Gestão tem permissão para acessar esta página.")
        return redirect('home')
    return _wrapped_view_func

class GestaoRequiredMixin:
    # Mixin para Class-Based Views que exige nível GESTAO
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == 'GESTAO':
            return super().dispatch(request, *args, **kwargs)
        messages.error(request, "Acesso negado: Apenas a Gestão tem permissão para acessar esta página.")
        return redirect('home')
