"""
URL patterns for voice_agent app
"""

from django.urls import path
from . import views

app_name = 'voice_agent'

urlpatterns = [
    # ── Exotel (legacy — kept for rollback) ──────────────────────────────────
    path('webhooks/exotel/status/', views.ExotelStatusWebhookView.as_view(), name='exotel_status'),
    path('make-call/', views.InitiateExotelCallView.as_view(), name='make_call'),

    # ── Local Recordings Server ──────────────────────────────────────────────
    path('api/calls/<str:call_sid>/recording/', views.CallRecordingAPI.as_view(), name='call_recording'),

    # ── Twilio (new platform) ────────────────────────────────────────────────
    path('webhooks/twilio/stream/', views.TwilioStreamView.as_view(), name='twilio_stream'),
    path('webhooks/twilio/status/', views.TwilioStatusWebhookView.as_view(), name='twilio_status'),
    path('webhooks/twilio/recording/', views.TwilioRecordingWebhookView.as_view(), name='twilio_recording'),
    path('twilio/make-call/', views.InitiateTwilioCallView.as_view(), name='twilio_make_call'),

    # ── Custom Web Dialer ──────────────────────────────────────────────────
    path('twilio/token/', views.TwilioTokenView.as_view(), name='twilio_token'),
    path('test-dialer/', views.WebDialerUI.as_view(), name='web_dialer'),
    path('webhooks/twilio/dialer-twiml/', views.WebDialerTwiMLView.as_view(), name='dialer_twiml'),

    # ── Doctor Dashboard ───────────────────────────────────────────────────
    path('dashboard/', views.DoctorDashboardUI.as_view(), name='dashboard'),
    path('login/', views.CustomLoginUI.as_view(), name='login'),
    path('logout/', views.CustomLogoutUI.as_view(), name='logout'),
    path('api/calls/<str:call_sid>/', views.CallDetailsAPI.as_view(), name='call_details'),
    path('api/booking/update/', views.UpdateBookingAPI.as_view(), name='update_booking'),
    path('api/kb/', views.KnowledgeBaseAPI.as_view(), name='kb_api'),
    path('api/kb/<str:kb_id>/', views.KnowledgeBaseDetailAPI.as_view(), name='kb_detail_api'),
    path('api/prompts/', views.SystemPromptsAPI.as_view(), name='prompts_api'),
]

