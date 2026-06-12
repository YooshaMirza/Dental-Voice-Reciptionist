"""
Batch Processor for AI Analysis
Queues recordings for batch processing to avoid interfering with live calls
"""

import asyncio
import logging
from typing import List, Dict
from utils.concurrency_tracker import concurrency_tracker
from utils.logger_formatter import box_header

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Manages batch processing of call recordings for AI analysis"""
    
    def __init__(self):
        self.pending_queue: List[Dict] = []
        self.processing = False
        self._check_task = None
    
    def add_to_queue(self, call_sid: str, call_end_time, retry_count: int = 0, max_retries: int = 2):
        """Add call to pending analysis queue with call end time"""
        self.pending_queue.append({
            'call_sid': call_sid,
            'call_end_time': call_end_time,
            'retry_count': retry_count,
            'max_retries': max_retries
        })
        logger.info(f"📋 Queued for batch: {call_sid} (Queue size: {len(self.pending_queue)})")
    
    async def try_start_batch(self):
        """Try to start batch processing if no active calls"""
        if self.processing:
            logger.info(f"⏸️ Batch already running (Queue: {len(self.pending_queue)})")
            return
        
        if len(self.pending_queue) == 0:
            return
        
        if len(self.pending_queue) == 0:
            return
        
        logger.info(f"✅ Starting batch processing for {len(self.pending_queue)} calls")
        
        # Start batch processing
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """Process all pending analyses"""
        self.processing = True
        batch_size = len(self.pending_queue)
        
        logger.info(box_header(
            f"🔄 BATCH PROCESSING STARTED\n"
            f"  Queue Size: {batch_size} calls\n"
            f"  Status: Processing..."
        ))
        
        processed = 0
        
        while self.pending_queue:
            
            # Process next item
            item = self.pending_queue.pop(0)
            call_sid = item['call_sid']
            call_end_time = item['call_end_time']
            retry_count = item.get('retry_count', 0)
            max_retries = item.get('max_retries', 2)
            
            try:
                logger.info(f"🔄 Processing [{processed + 1}/{batch_size}]: {call_sid[:20]}...")
                
                # Import here to avoid circular dependency
                from voice_agent.ai_analysis import process_recording_with_fetch
                
                # Process with URL fetching and smart wait
                success = await process_recording_with_fetch(
                    call_sid=call_sid,
                    call_end_time=call_end_time,
                    retry_count=retry_count,
                    max_retries=max_retries
                )
                
                if success:
                    processed += 1
                    logger.info(f"✅ Completed [{processed}/{batch_size}]: {call_sid[:20]}...")
                else:
                    # Re-queue if retry needed
                    if retry_count < max_retries:
                        logger.info(f"🔄 Re-queueing {call_sid[:20]} for retry")
                        self.pending_queue.append({
                            'call_sid': call_sid,
                            'call_end_time': call_end_time,
                            'retry_count': retry_count + 1,
                            'max_retries': max_retries
                        })
                
            except Exception as e:
                logger.error(f"❌ Batch processing error for {call_sid}: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Batch complete
        logger.info(box_header(
            f"✅ BATCH PROCESSING COMPLETE\n"
            f"  Processed: {processed} calls\n"
            f"  Status: All done!"
        ))
        
        self.processing = False


# Global instance
batch_processor = BatchProcessor()
