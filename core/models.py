from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser


class LogAuditoria(models.Model):
    ACOES = (
        ('CRIOU', 'Criou'),
        ('ALTEROU', 'Alterou'),
        ('EXCLUIU', 'Excluiu'),
    )
    quando = models.DateTimeField(auto_now_add=True, verbose_name="Quando")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Usuário")
    usuario_nome = models.CharField(max_length=150, blank=True, default='', verbose_name="Usuário (texto)")
    acao = models.CharField(max_length=10, choices=ACOES, verbose_name="Ação")
    modelo = models.CharField(max_length=60, verbose_name="Tipo de registro")
    objeto_id = models.CharField(max_length=40, blank=True, default='', verbose_name="ID do registro")
    descricao = models.CharField(max_length=255, verbose_name="Descrição")
    detalhes = models.JSONField(default=dict, blank=True, verbose_name="O que mudou")

    class Meta:
        verbose_name = "Log de Auditoria"
        verbose_name_plural = "Logs de Auditoria"
        ordering = ['-quando']

    def __str__(self):
        return f"{self.quando:%d/%m/%Y %H:%M} · {self.usuario_nome} {self.get_acao_display().lower()} {self.modelo}"


class Usuario(AbstractUser):
    ROLE_CHOICES = (
        ('GESTAO', 'Gestão / Administrador'),
        ('OPERADOR', 'Operador de Caixa / Atendente'),
    )
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='OPERADOR',
        verbose_name="Cargo / Nível de Acesso"
    )

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        ordering = ['username']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

