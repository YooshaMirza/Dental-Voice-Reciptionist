"""
AI Analysis Module
Handles transcription and sentiment analysis for Job Onboarding call recordings
"""

import asyncio
import logging
import tempfile
import os
import httpx
from datetime import datetime
from django.conf import settings
import google.generativeai as genai_sdk

from api.db import (
    update_call_transcript_sync,
    update_call_recording_sync,
    update_call_ai_status_sync,
    get_call_by_sid_sync,
    save_feedback_sync,
    save_firoz_lalani_data,
    calls_collection
)

logger = logging.getLogger(__name__)

async def process_recording_with_fetch(call_sid: str, call_end_time, retry_count: int = 0, max_retries: int = 2) -> bool:
    """Fetch recording URL from DB and process."""
    try:
        call_data = get_call_by_sid_sync(call_sid)
        
        if call_data and call_data.get('transcript') and call_data['transcript'].get('text'):
            logger.info(f"[call_{call_sid[:8]}] ✅ Already processed, skipping")
            return True
        
        time_since_end = (datetime.utcnow() - call_end_time).total_seconds()
        wait_needed = max(0, 15 - time_since_end)
        if wait_needed > 0:
            logger.info(f"[call_{call_sid[:8]}] ⏰ Waiting {int(wait_needed)}s for recording...")
            await asyncio.sleep(wait_needed)
        
        call_data = get_call_by_sid_sync(call_sid)
        recording_url = call_data.get('recording_url') if call_data else None
        
        if not recording_url:
            logger.warning(f"[call_{call_sid[:8]}] ⚠️ No recording URL found in DB (attempt {retry_count + 1}/{max_retries})")
            # If no DB recording url, check if we have a transcript from websocket text
            if call_data and call_data.get('transcript') and call_data['transcript'].get('text') and not call_data.get('ai_analysis'):
                logger.info(f"[call_{call_sid[:8]}] 📝 Found existing transcript text in DB. Proceeding with text-only AI analysis.")
                return await process_transcript_analysis_only(call_sid, call_data['transcript']['text'], call_data.get('customer_number') or call_data.get('phone_number'))
            return False
        
        return await process_recording_analysis(call_sid, recording_url)
        
    except Exception as e:
        logger.error(f"[call_{call_sid[:8]}] ❌ Error in fetch and process: {e}")
        return False

async def process_transcript_analysis_only(call_sid: str, transcript_text: str, phone_number: str) -> bool:
    """Run AI analysis directly on existing transcript text without needing an audio file."""
    try:
        await asyncio.to_thread(update_call_ai_status_sync, call_sid, 'processing')
        
        # If there are NO turns stored yet, let's parse them quickly
        turns = []
        for line in transcript_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('Agent:'):
                turns.append({'speaker': 'agent', 'text': line[6:].strip()})
            elif line.startswith('Alice:'):
                turns.append({'speaker': 'agent', 'text': line[6:].strip()})
            elif line.startswith('Dentina:'):
                turns.append({'speaker': 'agent', 'text': line[8:].strip()})
            elif line.startswith('Candidate:'):
                turns.append({'speaker': 'candidate', 'text': line[10:].strip()})
            elif line.startswith('Patient:'):
                turns.append({'speaker': 'candidate', 'text': line[8:].strip()})
            elif line.startswith('Human:'):
                turns.append({'speaker': 'candidate', 'text': line[6:].strip()})
            elif ':' in line:
                parts = line.split(':', 1)
                speaker = parts[0].strip().lower()
                text = parts[1].strip()
                if speaker in ['agent', 'alice', 'dentina', 'system', 'ai', 'advocate']:
                    turns.append({'speaker': 'agent', 'text': text})
                else:
                    turns.append({'speaker': 'candidate', 'text': text})
            else:
                turns.append({'speaker': 'candidate', 'text': line})
                
        if turns:
            await asyncio.to_thread(
                update_call_transcript_sync,
                call_sid=call_sid,
                transcript_text=transcript_text,
                transcript_turns=turns
            )
            
        await _analyze_with_ai(call_sid, transcript_text, phone_number)
        return True
    except Exception as e:
        logger.error(f"[call_{call_sid[:8]}] ❌ Error processing text analysis: {e}")
        return False

async def process_recording_analysis(call_sid: str, recording_url: str) -> bool:
    """Download, upload, transcribe, and analyze recording."""
    try:
        logger.info(f"🤖 [AI ANALYSIS] [START] Initiating analysis pipeline for Call SID: {call_sid}")
        logger.info(f"🤖 [AI ANALYSIS] [Step 1/4] Downloading audio recording from Twilio...")
        audio_content = None
        
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        auth = None
        if "twilio.com" in recording_url and account_sid and auth_token:
            auth = httpx.BasicAuth(account_sid, auth_token)
            logger.info("🔑 Configured HTTP Basic Authentication for Twilio recording download.")
        
        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    recording_response = await client.get(recording_url, auth=auth, timeout=60, follow_redirects=True)
                    if recording_response.status_code == 200 and recording_response.content:
                        audio_content = recording_response.content
                        break
                except Exception:
                    pass
                await asyncio.sleep(5 * (attempt + 1))

        if not audio_content:
            logger.error(f"❌ [AI ANALYSIS] Failed to download recording for {call_sid}")
            return False
            
        # Store downloaded binary content directly in MongoDB calls_collection
        logger.info(f"🤖 [AI ANALYSIS] [Step 2/4] Saving raw audio binary ({len(audio_content)} bytes) directly to MongoDB...")
        calls_collection.update_one(
            {"call_sid": call_sid},
            {"$set": {
                "recording_file_data": audio_content,
                "recording_file_saved_at": datetime.utcnow()
            }}
        )
        logger.info(f"💾 Saved binary audio recording directly to MongoDB for {call_sid}")
        
        call_data = await asyncio.to_thread(get_call_by_sid_sync, call_sid)
        duration = call_data.get('call_duration', 0) if call_data else 0
        
        if duration > 0 and duration <= 3:
            logger.info(f"[call_{call_sid[:8]}] ⚡ Skipping short call ({duration}s)")
            await asyncio.to_thread(update_call_ai_status_sync, call_sid, 'skipped_short_call')
            await asyncio.to_thread(
                update_call_recording_sync,
                call_sid=call_sid,
                recording_url=recording_url,
                recording_duration=duration
            )
            return True
            
        logger.info(f"🤖 [AI ANALYSIS] [Step 3/4] Transcribing audio content via Gemini...")
        await asyncio.to_thread(update_call_ai_status_sync, call_sid, 'processing')
        transcript_data = await _transcribe_with_gemini(call_sid, audio_content)
        
        if not transcript_data.get('success'):
            logger.error(f"❌ [AI ANALYSIS] Transcription failed for {call_sid}")
            return False
            
        await asyncio.to_thread(
            update_call_transcript_sync,
            call_sid=call_sid,
            transcript_text=transcript_data['full_text'],
            transcript_turns=transcript_data['turns']
        )
        
        logger.info(f"🤖 [AI ANALYSIS] [Step 4/4] Analyzing transcript text (sentiment, outcomes, details)...")
        await _analyze_with_ai(call_sid, transcript_data['full_text'], call_data.get('phone_number'))
        
        await asyncio.to_thread(
            update_call_recording_sync,
            call_sid=call_sid,
            recording_url=recording_url,
            recording_duration=duration
        )
        logger.info(f"🤖 [AI ANALYSIS] [FINAL] Call analysis completed successfully for Call SID: {call_sid}!")
        return True
        
    except Exception as e:
        logger.error(f"❌ [AI ANALYSIS] Error processing recording for {call_sid}: {e}")
        return False

async def _transcribe_with_gemini(call_sid: str, audio_content: bytes) -> dict:
    """Transcribe audio using Gemini."""
    try:
        import re
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            temp_file.write(audio_content)
            temp_path = temp_file.name
        
        genai_sdk.configure(api_key=settings.GEMINI_API_KEY)
        audio_file = genai_sdk.upload_file(path=temp_path)
        model = genai_sdk.GenerativeModel('gemini-2.5-flash')
        
        prompt = """Transcribe this dental clinic phone conversation accurately.
Separate the speakers as "Agent" (or "Alice" / "Dentina") and "Patient" (or "Customer").
Format:
Agent: ...
Patient: ...
Do not use markdown bolding (like **Agent:**) in speaker labels. Just write the name followed by a colon.
"""
        response = await asyncio.to_thread(model.generate_content, [prompt, audio_file])
        transcript_text = response.text.strip()
        
        try: os.unlink(temp_path)
        except: pass
        
        turns = []
        for line in transcript_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Clean markdown bolding (like **Agent:** or **Patient:**)
            cleaned_line = re.sub(r'^\*\*([^*]+)\*\*:', r'\1:', line).strip()
            cleaned_line = re.sub(r'^\*\*([^*]+)\*\*\s*:', r'\1:', cleaned_line).strip()
            cleaned_line = re.sub(r'^\*\*([^*:]+):', r'\1:', cleaned_line).strip()

            if cleaned_line.startswith('Agent:'):
                turns.append({'speaker': 'agent', 'text': cleaned_line[6:].strip()})
            elif cleaned_line.startswith('Alice:'):
                turns.append({'speaker': 'agent', 'text': cleaned_line[6:].strip()})
            elif cleaned_line.startswith('Dentina:'):
                turns.append({'speaker': 'agent', 'text': cleaned_line[8:].strip()})
            elif cleaned_line.startswith('Candidate:'):
                turns.append({'speaker': 'candidate', 'text': cleaned_line[10:].strip()})
            elif cleaned_line.startswith('Patient:'):
                turns.append({'speaker': 'candidate', 'text': cleaned_line[8:].strip()})
            elif cleaned_line.startswith('Customer:'):
                turns.append({'speaker': 'candidate', 'text': cleaned_line[9:].strip()})
            elif cleaned_line.startswith('Human:'):
                turns.append({'speaker': 'candidate', 'text': cleaned_line[6:].strip()})
            elif ':' in cleaned_line:
                parts = cleaned_line.split(':', 1)
                speaker = parts[0].strip().lower()
                text = parts[1].strip()
                speaker_clean = speaker.replace('*', '')
                if speaker_clean in ['agent', 'alice', 'dentina', 'system', 'ai', 'advocate']:
                    turns.append({'speaker': 'agent', 'text': text})
                else:
                    turns.append({'speaker': 'candidate', 'text': text})
            else:
                turns.append({'speaker': 'candidate', 'text': cleaned_line})
        
        return {'success': True, 'full_text': transcript_text, 'turns': turns}
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return {'success': False}

async def _analyze_with_ai(call_sid: str, transcript: str, phone_number: str = None):
    """Analyze transcript for Dental Call flow metrics."""
    try:
        model = genai_sdk.GenerativeModel('gemini-2.5-flash')
        prompt = f"""Analyze this dental office receptionist/advocate call transcript and provide a JSON response.

Transcript:
{transcript}

Provide JSON:
{{
  "sentiment": "positive" or "negative" or "neutral",
  "first_name": "Patient's first name if mentioned",
  "last_name": "Patient's last name if mentioned",
  "dob": "Patient's date of birth if mentioned",
  "zip_code": "Patient's residential ZIP code if mentioned",
  "support_person": "Emergency/support person name if mentioned",
  "appointment_type": "Type of appointment discussed (e.g. NP Cleaning, EP Cleaning, EP Treatment, NP Implant Consult)",
  "preferred_day": "Preferred day of the week if mentioned",
  "time_preference": "Preferred time (e.g. morning, afternoon) if mentioned",
  "selected_slot": "The selected appointment slot time if booked (ISO format or descriptive string)",
  "call_outcome": "Outcome of the call (e.g. Booked, Message, Transfer, Duplicate, Info)",
  "patient_status": "new_patient or existing_patient",
  "message_notes": "A brief summary of what the patient said and any messages for the office staff"
}}
"""
        response = await asyncio.to_thread(model.generate_content, prompt)
        import json, re
        json_match = re.search(r'\{[^}]+\}', response.text, re.DOTALL)
        if not json_match: return
        
        analysis = json.loads(json_match.group())
        
        # Save to firoz_lalani profile if phone exists
        if phone_number:
            patient_info = {
                "first_name": analysis.get('first_name'),
                "last_name": analysis.get('last_name'),
                "dob": analysis.get('dob'),
                "zip_code": analysis.get('zip_code'),
                "support_person": analysis.get('support_person'),
                "appointment_type": analysis.get('appointment_type'),
                "preferred_day": analysis.get('preferred_day'),
                "time_preference": analysis.get('time_preference'),
                "selected_slot": analysis.get('selected_slot'),
                "call_outcome": analysis.get('call_outcome'),
                "patient_status": analysis.get('patient_status'),
                "message_notes": analysis.get('message_notes'),
                "last_call_sentiment": analysis.get('sentiment')
            }
            await asyncio.to_thread(save_firoz_lalani_data, phone_number, patient_info)
            
        # Save general feedback
        await asyncio.to_thread(
            save_feedback_sync,
            call_sid=call_sid,
            sentiment=analysis.get('sentiment', 'neutral'),
            comment=analysis.get('message_notes', ''),
            onboarding_status=analysis.get('patient_status')
        )
        
        await asyncio.to_thread(
            update_call_ai_status_sync,
            call_sid,
            'completed',
            sentiment=analysis.get('sentiment', 'neutral'),
            conversation_summary=analysis.get('message_notes', '')
        )
    except Exception as e:
        logger.error(f"AI Analysis error: {e}")
        await asyncio.to_thread(update_call_ai_status_sync, call_sid, 'failed')
