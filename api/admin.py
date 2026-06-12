from django.contrib import admin
from .models import FirozLalani, KnowledgeBase, Prompt

@admin.register(FirozLalani)
class FirozLalaniAdmin(admin.ModelAdmin):
    list_display = ('phone', 'first_name', 'last_name', 'patient_status', 'call_outcome', 'appointment_type')
    search_fields = ('phone', 'first_name', 'last_name')

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('category', 'question', 'procedure_name', 'starting_price')
    list_filter = ('category',)
    search_fields = ('question', 'answer', 'keywords', 'procedure_name')

@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ('prompt_type', 'title', 'icon')
    search_fields = ('prompt_type', 'title', 'prompt_text')

