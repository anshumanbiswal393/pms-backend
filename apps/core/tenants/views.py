from rest_framework import viewsets, permissions, status
from apps.core.tenants.models import (
    Tenant, Property, TenantBranding, TenantDomain, 
    TenantConfiguration, TenantIsolationConfig
)
from apps.core.tenants.serializers import (
    TenantSerializer, PropertySerializer, TenantBrandingSerializer, TenantDomainSerializer,
    TenantConfigurationSerializer, TenantIsolationConfigSerializer, SuperadminPropertySerializer
)

from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

class TenantViewSet(viewsets.ModelViewSet):
    """
    Super-Admin CRUD endpoint for managing Tenants.
    """
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAdminUser]  # Only django admin/superusers can manage tenants directly

    def perform_create(self, serializer):
        tenant = serializer.save(
            created_by=self.request.user if self.request.user.is_authenticated else None
        )
        try:
            from django.core.management import call_command
            call_command('seed_product_access')
        except Exception:
            pass


class SuperadminPropertyViewSet(viewsets.ModelViewSet):
    """
    Super-Admin CRUD endpoint for managing Properties across all tenants.
    """
    queryset = Property.objects.all()
    serializer_class = SuperadminPropertySerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        prop = serializer.save(created_by=user)
        try:
            from apps.booking.sync import sync_pms_property_to_booking_engine
            sync_pms_property_to_booking_engine(prop)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to sync property to booking engine on create: {e}")
        try:
            from apps.core.subscriptions.services import ProductAccessService
            ProductAccessService.provision_tenant_products(prop, created_by=user)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to auto-provision tenant products: {e}")

    def perform_update(self, serializer):
        prop = serializer.save(
            updated_by=self.request.user if self.request.user.is_authenticated else None
        )
        try:
            from apps.booking.sync import sync_pms_property_to_booking_engine
            sync_pms_property_to_booking_engine(prop)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to sync property to booking engine on update: {e}")

    @action(detail=False, methods=['post'], url_path='upload-image')
    def upload_image(self, request):
        from django.core.files.storage import FileSystemStorage
        import os
        from django.conf import settings
        from rest_framework.response import Response
        from rest_framework import status
        
        file_obj = request.FILES.get('image')
        if not file_obj:
            return Response({'error': 'No file uploaded'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Ensure media directory exists
        media_dir = os.path.join(settings.MEDIA_ROOT, 'properties')
        os.makedirs(media_dir, exist_ok=True)
        
        fs = FileSystemStorage(location=media_dir, base_url=settings.MEDIA_URL + 'properties/')
        filename = fs.save(file_obj.name, file_obj)
        file_url = request.build_absolute_uri(fs.url(filename))
        
        return Response({'image_url': file_url}, status=status.HTTP_201_CREATED)



class PropertyViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoint for managing Properties under the resolved tenant context.
    """
    serializer_class = PropertySerializer
    
    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return Property.objects.none()
        
        if not user or not user.is_authenticated:
            return Property.objects.filter(tenant=tenant)

        # Superuser bypass: allow viewing specific tenant or all if explicitly requested
        if user.is_superuser:
            tenant_param = self.request.query_params.get('tenant') or self.request.headers.get('X-Tenant-ID')
            if tenant_param:
                return Property.objects.filter(tenant_id=tenant_param)
            return Property.objects.filter(tenant=tenant)

        # Tenant Owner / Director / Admin - strictly isolated to their own tenant
        is_owner = (
            user.is_staff or
            (user.role and user.role.code in ['owner', 'tenant_owner', 'admin', 'super_admin'])
        )
        if is_owner:
            return Property.objects.filter(tenant=tenant)

        # Filter assigned properties for staff users within their tenant
        from apps.core.accounts.models import UserAssignment
        from apps.core.rbac.models import UserPropertyRole

        assigned_ids = set()
        for ua in UserAssignment.objects.filter(user=user, tenant=tenant):
            if ua.property_id:
                assigned_ids.add(ua.property_id)
        for upr in UserPropertyRole.objects.filter(user=user, tenant=tenant):
            if upr.property_id:
                assigned_ids.add(upr.property_id)

        if assigned_ids:
            return Property.objects.filter(tenant=tenant, id__in=assigned_ids)

        return Property.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        property_obj = serializer.save(
            tenant=tenant,
            created_by=self.request.user if self.request.user.is_authenticated else None
        )
        try:
            from apps.booking.sync import sync_pms_property_to_booking_engine
            sync_pms_property_to_booking_engine(property_obj)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to sync property to booking engine on create: {e}")
        # Automatically assign the creator to the new property as owner
        if self.request.user and self.request.user.is_authenticated:
            from apps.core.rbac.models import Role, UserPropertyRole
            owner_role = Role.objects.filter(tenant=tenant, code='owner').first()
            if owner_role:
                UserPropertyRole.objects.get_or_create(
                    tenant=tenant,
                    user=self.request.user,
                    property=property_obj,
                    role=owner_role
                )
        
    def perform_update(self, serializer):
        property_obj = serializer.save(
            updated_by=self.request.user if self.request.user.is_authenticated else None
        )
        try:
            from apps.booking.sync import sync_pms_property_to_booking_engine
            sync_pms_property_to_booking_engine(property_obj)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to sync property to booking engine on update: {e}")

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_photo(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file was provided.'}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.core.files.storage import default_storage
        import os
        import uuid
        
        ext = os.path.splitext(file_obj.name)[1]
        unique_filename = f"properties/{uuid.uuid4()}{ext}"
        saved_path = default_storage.save(unique_filename, file_obj)
        file_url = request.build_absolute_uri(default_storage.url(saved_path))
        
        return Response({'url': file_url}, status=status.HTTP_201_CREATED)


class TenantBrandingViewSet(viewsets.ModelViewSet):
    serializer_class = TenantBrandingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantBranding.objects.none()
        return TenantBranding.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


class TenantDomainViewSet(viewsets.ModelViewSet):
    serializer_class = TenantDomainSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantDomain.objects.none()
        return TenantDomain.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


class TenantConfigurationViewSet(viewsets.ModelViewSet):
    serializer_class = TenantConfigurationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantConfiguration.objects.none()
        
        # Auto-create if missing for seed/existing tenants
        TenantConfiguration.objects.get_or_create(
            tenant=tenant,
            defaults={
                'timezone': getattr(tenant, 'timezone', 'UTC') or 'UTC',
                'currency': getattr(tenant, 'currency', 'USD') or 'USD',
                'language': 'en',
                'mfa_double_confirmation': True
            }
        )
        return TenantConfiguration.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


class TenantIsolationConfigViewSet(viewsets.ModelViewSet):
    serializer_class = TenantIsolationConfigSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantIsolationConfig.objects.none()
        return TenantIsolationConfig.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


from rest_framework.views import APIView
from rest_framework.response import Response

class RequestSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized.'}, status=403)
        from apps.core.subscriptions.models import SubscriptionRequest
        requests_qs = SubscriptionRequest.objects.all().order_by('-created_at')
        data = [{
            'id': str(r.id),
            'tenant_name': r.tenant.name,
            'tenant_subdomain': r.tenant.subdomain,
            'product_name': r.product_name,
            'contact_name': r.contact_name,
            'contact_email': r.contact_email,
            'comments': r.comments,
            'status': r.status,
            'created_at': r.created_at.isoformat()
        } for r in requests_qs]
        return Response(data, status=200)

    def post(self, request):
        tenant = getattr(request.user, 'tenant', None) or getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=400)
        
        product_name = request.data.get('product_name')
        contact_name = request.data.get('contact_name') or request.user.name
        contact_email = request.data.get('contact_email') or request.user.email
        comments = request.data.get('comments', '')

        if not product_name:
            return Response({'error': 'Product name is required.'}, status=400)

        # Save to database
        from apps.core.subscriptions.models import SubscriptionRequest
        sub_req = SubscriptionRequest.objects.create(
            tenant=tenant,
            product_name=product_name,
            contact_name=contact_name,
            contact_email=contact_email,
            comments=comments
        )

        # Get all superadmins to notify
        from apps.core.accounts.models import AppUser
        admin_emails = list(AppUser.objects.filter(is_superuser=True).values_list('email', flat=True))
        if not admin_emails:
            admin_emails = ['admin@retrod.com']

        # Render a professional HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
            .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 30px; max-width: 600px; margin: 0 auto; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
            .header {{ border-bottom: 2px solid #3b82f6; padding-bottom: 15px; margin-bottom: 20px; }}
            .header h2 {{ margin: 0; color: #1d4ed8; font-size: 20px; }}
            .detail-row {{ display: flex; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; }}
            .label {{ font-weight: bold; width: 140px; color: #475569; }}
            .value {{ flex: 1; color: #0f172a; }}
            .comments-box {{ background: #f8fafc; border: 1px dashed #cbd5e1; padding: 12px; border-radius: 6px; margin-top: 15px; font-style: italic; }}
            .footer {{ text-align: center; margin-top: 25px; font-size: 11px; color: #64748b; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="header">
              <h2>New Subscription Request</h2>
            </div>
            <div class="detail-row">
              <div class="label">Product:</div>
              <div class="value" style="font-weight: bold; color: #2563eb;">{product_name}</div>
            </div>
            <div class="detail-row">
              <div class="label">Tenant / Partner:</div>
              <div class="value">{tenant.name} ({tenant.subdomain})</div>
            </div>
            <div class="detail-row">
              <div class="label">Requested By:</div>
              <div class="value">{contact_name}</div>
            </div>
            <div class="detail-row">
              <div class="label">Contact Email:</div>
              <div class="value"><a href="mailto:{contact_email}">{contact_email}</a></div>
            </div>
            {f'<div class="comments-box"><strong>Comments:</strong><br/>{comments}</div>' if comments else ''}
            <div class="footer">
              This request was generated automatically from Retrod One partner panel.
            </div>
          </div>
        </body>
        </html>
        """

        from django.core.mail import send_mail
        from django.conf import settings
        
        send_mail(
            subject=f"Subscription Request: {product_name} - {tenant.name}",
            message=f"New subscription request for {product_name} from {tenant.name}.",
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@retrod.io'),
            recipient_list=admin_emails,
            html_message=html_content,
            fail_silently=True
        )

        return Response({'message': 'Subscription request sent successfully.', 'id': str(sub_req.id)}, status=200)

    def patch(self, request):
        if not request.user.is_superuser:
            return Response({'error': 'Unauthorized.'}, status=403)
        request_id = request.data.get('id')
        new_status = request.data.get('status')
        if not request_id or not new_status:
            return Response({'error': 'ID and status are required.'}, status=400)
        from apps.core.subscriptions.models import (
            SubscriptionRequest, Product, TenantSubscription, TenantProduct,
            TenantProductLicense, TenantProductEntitlement, ProductFeature,
            TenantSubscriptionFeature
        )
        from apps.core.accounts.models import AppUser
        from django.utils import timezone
        import uuid

        try:
            req_obj = SubscriptionRequest.objects.get(id=request_id)
            req_obj.status = new_status
            req_obj.save()

            # If request is APPROVED, assign/provision the requested product & features to the tenant
            if new_status == 'APPROVED':
                tenant = req_obj.tenant
                product_name = req_obj.product_name

                # 1. Match product by name or code
                product = Product.objects.filter(name__iexact=product_name).first() or \
                          Product.objects.filter(code__iexact=product_name).first()

                if not product:
                    product = Product.objects.filter(name__icontains=product_name).first() or \
                              Product.objects.filter(code__icontains=product_name).first()

                if product:
                    # 2. Get or create tenant's active subscription
                    active_sub = TenantSubscription.objects.filter(tenant=tenant, status='ACTIVE').first()
                    if not active_sub:
                        start_d = timezone.now().date()
                        end_d = start_d + timezone.timedelta(days=365)
                        active_sub = TenantSubscription.objects.create(
                            tenant=tenant,
                            plan=None,
                            is_custom=True,
                            custom_name=f"Standard Custom Plan ({tenant.name})",
                            billing_cycle='MONTHLY',
                            price=0.00,
                            currency='USD',
                            start_date=start_d,
                            end_date=end_d,
                            status='ACTIVE'
                        )

                    # 3. Provision TenantProduct
                    start_date = active_sub.start_date or timezone.now().date()
                    end_date = active_sub.end_date or (start_date + timezone.timedelta(days=365))

                    tp, _ = TenantProduct.objects.update_or_create(
                        tenant=tenant,
                        product=product,
                        defaults={
                            'tenant_subscription': active_sub,
                            'activated_at': timezone.now(),
                            'expires_at': timezone.datetime.combine(end_date, timezone.datetime.min.time()),
                            'status': 'ACTIVE'
                        }
                    )

                    # 4. Provision TenantProductLicense
                    superuser = AppUser.objects.filter(is_superuser=True).first()
                    lic = TenantProductLicense.objects.filter(tenant_product=tp).first()
                    if not lic:
                        TenantProductLicense.objects.create(
                            tenant_product=tp,
                            status='ACTIVE',
                            license_key=f"LIC-{product.code.upper()}-{uuid.uuid4().hex[:12].upper()}",
                            start_date=start_date,
                            end_date=end_date,
                            issued_by=superuser
                        )
                    else:
                        lic.status = 'ACTIVE'
                        lic.save()

                    # 5. Provision Features & Entitlements for this product
                    product_features = ProductFeature.objects.filter(product=product)

                    # If subscription is custom, register custom features on subscription
                    if active_sub.is_custom:
                        for pf in product_features:
                            TenantSubscriptionFeature.objects.get_or_create(
                                tenant_subscription=active_sub,
                                product_feature=pf,
                                defaults={
                                    'feature_code': pf.code,
                                    'price': pf.price or 0.00,
                                    'is_active': True
                                }
                            )

                    # Provision TenantProductEntitlement records
                    for pf in product_features:
                        TenantProductEntitlement.objects.update_or_create(
                            tenant_product=tp,
                            feature_code=pf.code,
                            defaults={
                                'product_feature': pf,
                                'limit_type': 'BOOLEAN',
                                'limit_value_boolean': True
                            }
                        )

                # Send approval email to requested user/contact
                if req_obj.contact_email:
                    from django.core.mail import send_mail
                    from django.conf import settings

                    email_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <body style="font-family: Arial, sans-serif; padding: 20px; background: #f8fafc;">
                      <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; max-width: 550px; margin: 0 auto;">
                        <h3 style="color: #166534; margin-top: 0;">Subscription Request Approved!</h3>
                        <p>Hello <strong>{req_obj.contact_name}</strong>,</p>
                        <p>Your subscription request for <strong>{req_obj.product_name}</strong> for <strong>{tenant.name}</strong> has been approved and activated by the platform administrator.</p>
                        <p>The module is now enabled and accessible in your Retrod One dashboard.</p>
                        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                        <p style="font-size: 11px; color: #64748b;">Retrod One Hospitality Platform</p>
                      </div>
                    </body>
                    </html>
                    """

                    send_mail(
                        subject=f"Subscription Request Approved: {req_obj.product_name}",
                        message=f"Your subscription request for {req_obj.product_name} has been approved and activated.",
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@retrod.io'),
                        recipient_list=[req_obj.contact_email],
                        html_message=email_html,
                        fail_silently=True
                    )

            return Response({'message': f'Subscription request {new_status.lower()} and product assigned successfully.'}, status=200)
        except SubscriptionRequest.DoesNotExist:
            return Response({'error': 'Request not found.'}, status=404)

