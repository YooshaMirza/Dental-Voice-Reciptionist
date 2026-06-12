from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    FeedbackCallView, StopFeedbackCallView, CallStatusView, SingleCallStatusView, CustomSignupView,
    CustomLoginView, OtpLoginView, RequestOtpView, VerifyOtpView, ResendOtpView, CustomUserView, 
    ProcessRecordingView, GetRecordingView,
    SingleCallView, RetryAnalysisView, StartCallView,
    UserProfileImageView, CallStatsView,
    PromptListCreateView, PromptDetailView,
)
from .twilio_views import twilio_inbound_handler, twilio_outbound_handler

urlpatterns = [
    # Authentication endpoints
    path('auth/signup/', CustomSignupView.as_view(), name='auth-signup'),
    path('auth/request-otp/', RequestOtpView.as_view(), name='auth-request-otp'),
    path('auth/verify-otp/', VerifyOtpView.as_view(), name='auth-verify-otp'),
    path('auth/resend-otp/', ResendOtpView.as_view(), name='auth-resend-otp'),
    path('auth/login/', CustomLoginView.as_view(), name='auth-login'),
    path('auth/login-otp/', OtpLoginView.as_view(), name='auth-login-otp'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/user/', CustomUserView.as_view(), name='auth-user'),
    path('auth/user/profile-image/', UserProfileImageView.as_view(), name='auth-user-profile-image'),
    path('auth/user-profile-image/', UserProfileImageView.as_view(), name='auth-user-profile-image-alias'),
    
    path('prompts/', PromptListCreateView.as_view(), name='prompts'),
    path('prompts/<str:prompt_type>/', PromptDetailView.as_view(), name='prompt-detail'),
    
    # Call endpoints
    path('calls/start/', StartCallView.as_view(), name='start-call'),
    path('calls/feedback/', FeedbackCallView.as_view(), name='feedback-call'),
    path('calls/feedback/stop/', StopFeedbackCallView.as_view(), name='stop-feedback-call'),
    path('calls/single/', SingleCallView.as_view(), name='single-call'),
    path('calls/status/', CallStatusView.as_view(), name='call-status'),
    path('calls/single/status/', SingleCallStatusView.as_view(), name='single-call-status'),
    path('calls/stats/', CallStatsView.as_view(), name='call-stats'),
    path('calls/retry-analysis/', RetryAnalysisView.as_view(), name='retry-analysis'),
    
    path('calls/process-recording/', ProcessRecordingView.as_view(), name='process-recording'),
    path('calls/recording/', GetRecordingView.as_view(), name='get-recording'),

    # Twilio Webhooks
    path('twilio/inbound/', twilio_inbound_handler, name='twilio-inbound'),
    path('twilio/outbound/', twilio_outbound_handler, name='twilio-outbound'),
]