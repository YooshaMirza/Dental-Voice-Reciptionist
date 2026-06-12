from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/?$', consumers.VoiceAgentConsumer.as_asgi()),  # Matches both /ws and /ws/
    re_path(r'^ws/twilio/?$', consumers.VoiceAgentConsumer.as_asgi()),
]