from django.urls import path
from . import views

urlpatterns = [
    path("", views.chatbot_info_view, name="chatbot_info_root"),
    path("whatsapp/", views.chatbot_info_view, name="chatbot_info_whatsapp"),
    path("whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("whatsapp/staff/", views.staff_whatsapp_webhook, name="whatsapp_staff_webhook"),
    path("whatsapp/guest/", views.guest_whatsapp_webhook, name="whatsapp_guest_webhook"),
    path("twilio/webhook/", views.whatsapp_webhook, name="twilio_webhook"),
    path("twilio/staff/", views.staff_whatsapp_webhook, name="twilio_staff_webhook"),
    path("twilio/guest/", views.guest_whatsapp_webhook, name="twilio_guest_webhook"),
]
