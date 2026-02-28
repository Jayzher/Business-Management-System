from django.db import models
from django.contrib.auth.models import AbstractUser
from core.models import TimeStampedModel


class User(AbstractUser):
    """Custom user model with additional fields."""
    phone = models.CharField(max_length=20, blank=True, default='')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    class Meta:
        db_table = 'auth_user'

    def __str__(self):
        return self.get_full_name() or self.username


class Role(TimeStampedModel):
    """Application-level roles (Admin, Warehouse Manager, Encoder, Checker, Viewer)."""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserRole(TimeStampedModel):
    """Many-to-many between User and Role."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_users')

    class Meta:
        unique_together = ('user', 'role')

    def __str__(self):
        return f"{self.user} - {self.role}"


class WarehousePermission(TimeStampedModel):
    """Per-warehouse access control."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='warehouse_permissions')
    warehouse = models.ForeignKey(
        'warehouses.Warehouse', on_delete=models.CASCADE, related_name='user_permissions'
    )
    can_view = models.BooleanField(default=True)
    can_receive = models.BooleanField(default=False)
    can_deliver = models.BooleanField(default=False)
    can_transfer = models.BooleanField(default=False)
    can_adjust = models.BooleanField(default=False)
    can_manage = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'warehouse')

    def __str__(self):
        return f"{self.user} @ {self.warehouse}"
