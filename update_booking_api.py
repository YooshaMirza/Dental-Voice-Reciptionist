class UpdateBookingAPI(APIView):
    def post(self, request):
        try:
            patient_id = request.data.get('patient_id')
            status_val = request.data.get('status')
            
            if not patient_id or status_val not in ['confirmed', 'declined']:
                return JsonResponse({'success': False, 'error': 'Invalid parameters'}, status=400)
            
            patient = FirozLalani.objects.get(_id=ObjectId(patient_id))
            patient.booking_status = status_val
            
            if status_val == 'confirmed':
                ghl_api_key = getattr(settings, 'GHL_API_KEY', '')
                if ghl_api_key and patient.selected_slot:
                    patient.ghl_appointment_id = 'ghl_apt_' + str(time.time()).replace('.', '')[:10]
            
            patient.save()
            return JsonResponse({'success': True, 'booking_status': patient.booking_status})
            
        except FirozLalani.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Patient not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
