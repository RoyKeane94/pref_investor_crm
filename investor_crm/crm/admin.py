from django.contrib import admin

from .models import (
    CallLog,
    CoInvestment,
    Contact,
    EmailLog,
    InfoLink,
    Intermediary,
    Investor,
    MeetingLog,
    Office,
    OtherCommitment,
    Reminder,
    Responsibility,
)


@admin.register(Responsibility)
class ResponsibilityAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Intermediary)
class IntermediaryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'principal_contact',
        'statuses',
        'ticket_size',
        'office',
        'responsibility',
        'intermediary',
        'vdr_access',
    )
    list_filter = ('responsibility', 'office', 'intermediary', 'vdr_access')
    search_fields = ('name', 'principal_contact', 'office__name')


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'investor', 'role', 'email')
    search_fields = ('name', 'email', 'investor__name')


@admin.register(MeetingLog)
class MeetingLogAdmin(admin.ModelAdmin):
    list_display = ('investor', 'date', 'participants_display', 'created_at')
    list_filter = ('date',)
    search_fields = ('investor__name', 'notes')


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('investor', 'date', 'with_display', 'created_at')
    list_filter = ('date',)
    search_fields = ('investor__name', 'contact_name_override', 'notes')


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ('investor', 'date', 'with_display', 'direction', 'subject')
    list_filter = ('direction', 'date')
    search_fields = ('investor__name', 'contact_name_override', 'subject', 'notes')


@admin.register(OtherCommitment)
class OtherCommitmentAdmin(admin.ModelAdmin):
    list_display = ('investor', 'fund', 'amount', 'date')


@admin.register(InfoLink)
class InfoLinkAdmin(admin.ModelAdmin):
    list_display = ('investor', 'title', 'link')


@admin.register(CoInvestment)
class CoInvestmentAdmin(admin.ModelAdmin):
    list_display = ('investor', 'name', 'size', 'decision', 'date')
    list_filter = ('decision',)


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('investor', 'description', 'due_date', 'is_done')
    list_filter = ('is_done', 'due_date')
