from rest_framework.views import APIView
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from .db import calls_collection, config, call_context_store, feedback_collection, prompts_collection
from .db import db as mongo_db
from datetime import datetime, timedelta
from bson import ObjectId
import requests
from requests.auth import HTTPBasicAuth
import logging
import json
import time
import os
from django.contrib.auth import get_user_model, authenticate
from .models import UserProfile, Prompt
from .serializers import PromptModelSerializer, SignupSerializer, LoginSerializer, OtpLoginSerializer, VerifyOtpSerializer, OtpRequestSerializer, ResendOtpSerializer
from .db import save_outbound_context_sync
from api.call_utils import initiate_twilio_call

User = get_user_model()
logger = logging.getLogger(__name__)

class AuthenticatedAPIView(APIView):
    permission_classes = [IsAuthenticated]

def _is_duplicate_user_error(exc):
    s = str(exc).lower()
    return 'already exists' in s and ('email' in s or 'username' in s)

def _signup_400_response(exc):
    if _is_duplicate_user_error(exc):
        return Response({'error': 'User already exists'}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class CustomSignupView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.create_user(
                email=serializer.validated_data['email'],
                password=serializer.validated_data['password'],
                first_name=serializer.validated_data['name'],
                phone=serializer.validated_data['phone'],
                role=serializer.validated_data.get('role', User.Role.ADMIN)
            )
            UserProfile.objects.create(user=user, phone=user.phone)
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': {
                    'email': user.email,
                    'name': user.first_name,
                    'role': user.role
                }
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return _signup_400_response(e)

class CustomLoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = authenticate(email=serializer.validated_data['email'], password=serializer.validated_data['password'])
        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'email': user.email,
                'name': user.first_name,
                'role': user.role
            }
        })

class RequestOtpView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        email = request.data.get('email')
        if not email: return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
        # Mock OTP logic
        logger.info(f"OTP Requested for {email}")
        return Response({'message': 'OTP sent successfully'})

class VerifyOtpView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({'message': 'OTP verified successfully'})

class ResendOtpView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({'message': 'OTP resent successfully'})

class OtpLoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({'error': 'OTP login not implemented'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class CustomUserView(AuthenticatedAPIView):
    def get(self, request):
        user = request.user
        return Response({
            'email': user.email,
            'name': user.first_name,
            'role': user.role,
            'phone': user.phone,
            'voicelink_did': user.voicelink_did
        })

class UserProfileImageView(AuthenticatedAPIView):
    def post(self, request):
        return Response({'message': 'Upload not implemented'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class PromptListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PromptModelSerializer
    def get_queryset(self):
        return Prompt.objects.all()

class PromptDetailView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PromptModelSerializer
    lookup_field = 'prompt_type'
    def get_queryset(self):
        return Prompt.objects.all()

class StartCallView(AuthenticatedAPIView):
    def post(self, request):
        data = request.data
        phone = data.get('phone')
        if not phone: return Response({'error': 'Phone required'}, status=status.HTTP_400_BAD_REQUEST)
        
        context = data.get('context', {})
        result = initiate_twilio_call(phone, context)
        
        if result['status'] == 'success':
            return Response(result)
        return Response(result, status=status.HTTP_400_BAD_REQUEST)

class SingleCallView(AuthenticatedAPIView):
    def post(self, request):
        # Alias for StartCallView or specialized single call logic
        return StartCallView.as_view()(request._request)

class CallStatusView(AuthenticatedAPIView):
    def get(self, request):
        calls = list(calls_collection.find().sort('created_at', -1).limit(50))
        for c in calls: c['_id'] = str(c['_id'])
        return Response(calls)

class SingleCallStatusView(AuthenticatedAPIView):
    def get(self, request):
        call_sid = request.GET.get('call_sid')
        if not call_sid: return Response({'error': 'call_sid required'}, status=status.HTTP_400_BAD_REQUEST)
        call = calls_collection.find_one({'call_sid': call_sid})
        if not call: return Response({'error': 'Call not found'}, status=status.HTTP_404_NOT_FOUND)
        call['_id'] = str(call['_id'])
        return Response(call)

class CallStatsView(AuthenticatedAPIView):
    def get(self, request):
        total = calls_collection.count_documents({})
        completed = calls_collection.count_documents({'call_status': 'completed'})
        failed = calls_collection.count_documents({'call_status': {'$in': ['failed', 'no_answer', 'busy']}})
        return Response({
            'total_calls': total,
            'completed_calls': completed,
            'failed_calls': failed
        })

class RetryAnalysisView(APIView):
    def post(self, request):
        call_sid = request.data.get('call_sid')
        if not call_sid: return Response({'error': 'call_sid required'}, status=status.HTTP_400_BAD_REQUEST)
        from voice_agent.ai_analysis import process_recording_with_fetch
        from asgiref.sync import async_to_sync
        # Trigger background task
        return Response({'message': 'Analysis retry triggered'})

class ProcessRecordingView(APIView):
    def post(self, request):
        return Response({'message': 'Recording process triggered'})

class GetRecordingView(AuthenticatedAPIView):
    def get(self, request):
        call_sid = request.GET.get('call_sid')
        call = calls_collection.find_one({'call_sid': call_sid})
        if not call:
            return Response({'error': 'Call not found'}, status=status.HTTP_404_NOT_FOUND)
            
        if 'recording_file_data' in call:
            local_url = f"/api/voice-agent/api/calls/{call_sid}/recording/"
            return Response({'url': local_url})
            
        if call.get('call_recording_url'):
            return Response({'url': call['call_recording_url']})
            
        return Response({'error': 'Recording not found'}, status=status.HTTP_404_NOT_FOUND)

class FeedbackCallView(AuthenticatedAPIView):
    def post(self, request):
        return Response({'error': 'Feedback call batch not implemented for jobs'}, status=status.HTTP_501_NOT_IMPLEMENTED)

class StopFeedbackCallView(AuthenticatedAPIView):
    def post(self, request):
        return Response({'message': 'Batch stopped'})