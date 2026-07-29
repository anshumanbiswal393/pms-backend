from django.db import models
from rest_framework import viewsets, permissions
from apps.core.reference.models import Country, Nationality, Language, Currency, DocumentType, ReservationSource, Timezone, State
from apps.core.reference.serializers import (
    CountrySerializer, NationalitySerializer, LanguageSerializer,
    CurrencySerializer, DocumentTypeSerializer, ReservationSourceSerializer, TimezoneSerializer,
    StateSerializer
)
from apps.core.reference.permissions import IsSuperUserOrReadOnly

class CountryViewSet(viewsets.ModelViewSet):
    serializer_class = CountrySerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = Country.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class NationalityViewSet(viewsets.ModelViewSet):
    serializer_class = NationalitySerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = Nationality.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class LanguageViewSet(viewsets.ModelViewSet):
    serializer_class = LanguageSerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = Language.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class CurrencyViewSet(viewsets.ModelViewSet):
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Currency.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class DocumentTypeViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentTypeSerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = DocumentType.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class ReservationSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSourceSerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = ReservationSource.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class TimezoneViewSet(viewsets.ModelViewSet):
    serializer_class = TimezoneSerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = Timezone.objects.all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset


class StateViewSet(viewsets.ModelViewSet):
    serializer_class = StateSerializer
    permission_classes = [IsSuperUserOrReadOnly]

    def get_queryset(self):
        queryset = State.objects.all()
        country_id = self.request.query_params.get('country')
        if country_id:
            queryset = queryset.filter(country_id=country_id)
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(code__icontains=search)
            )
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', '1'])
        return queryset
