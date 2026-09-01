"""Guarda o usuário da requisição atual num contexto por thread, para que os
signals de auditoria saibam quem fez a alteração."""
import threading

_estado = threading.local()


def get_usuario_atual():
    return getattr(_estado, 'usuario', None)


class UsuarioAtualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _estado.usuario = getattr(request, 'user', None)
        try:
            return self.get_response(request)
        finally:
            _estado.usuario = None
