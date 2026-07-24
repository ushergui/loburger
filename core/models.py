from django.db import models
from django.contrib.auth.models import AbstractUser

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

