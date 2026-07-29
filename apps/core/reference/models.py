from django.db import models
from apps.core.common.models import BaseModel

class Country(BaseModel):
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    phone_code = models.CharField(max_length=16, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Countries"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Nationality(BaseModel):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Nationalities"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Language(BaseModel):
    code = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Currency(BaseModel):
    code = models.CharField(max_length=3, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    symbol = models.CharField(max_length=10, null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='currencies')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class DocumentType(BaseModel):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ReservationSource(BaseModel):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class Timezone(BaseModel):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    utc_offset = models.CharField(max_length=10, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"


class State(BaseModel):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    code = models.CharField(max_length=10, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('country', 'code')

    def __str__(self):
        return f"{self.name}, {self.country.name}"

