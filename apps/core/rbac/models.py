import uuid
from django.db import models
from django.conf import settings
from apps.core.tenants.models import Tenant, Property

class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    category = models.CharField(max_length=64)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.category}:{self.code}"

class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='roles')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('tenant', 'code')

    def __str__(self):
        if self.tenant:
            return f"{self.name} ({self.tenant.name})"
        return f"{self.name} (Global)"

class RolePermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='roles')

    class Meta:
        unique_together = ('role', 'permission')

    def __str__(self):
        return f"{self.role.code} -> {self.permission.code}"

class UserPropertyRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='user_property_roles')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='property_roles')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_properties')

    class Meta:
        unique_together = ('user', 'property', 'role')

    def __str__(self):
        return f"{self.user} @ {self.property.name} as {self.role.name}"
