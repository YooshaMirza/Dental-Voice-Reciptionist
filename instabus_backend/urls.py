from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from api.views import CustomSignupView, CustomLoginView, CustomUserView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('api/voice-agent/', include('voice_agent.urls')),  # Voice agent endpoints
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
]

# This is the safe way to serve static files in development
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()