from django.contrib import admin, messages

from .models import (
    AgentApiToken,
    AgentNote,
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
from .permissions import is_agent_user


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
    list_display = ('name', 'investor', 'role', 'email', 'is_ex')
    list_filter = ('is_ex',)
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


@admin.register(AgentNote)
class AgentNoteAdmin(admin.ModelAdmin):
    list_display = (
        'investor',
        'note_type',
        'title',
        'author',
        'person_name',
        'event_date',
        'confidence',
        'created_at',
    )
    list_filter = ('note_type', 'confidence', 'created_at')
    search_fields = (
        'investor__name',
        'title',
        'body',
        'link',
        'person_name',
        'moved_from',
        'moved_to',
        'author__email',
    )
    raw_id_fields = ('investor', 'author')


@admin.register(AgentApiToken)
class AgentApiTokenAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'user',
        'prefix',
        'is_active',
        'created_at',
        'last_used_at',
        'revoked_at',
    )
    list_filter = ('revoked_at', 'created_at')
    search_fields = ('name', 'prefix', 'user__email', 'user__username')
    raw_id_fields = ('user',)
    readonly_fields = (
        'prefix',
        'key_hash',
        'created_at',
        'last_used_at',
        'revoked_at',
    )
    actions = ('revoke_tokens',)

    @admin.display(boolean=True, description='Active')
    def is_active(self, obj: AgentApiToken) -> bool:
        return obj.is_active

    @admin.action(description='Revoke selected tokens')
    def revoke_tokens(self, request, queryset):
        count = 0
        for token in queryset.filter(revoked_at__isnull=True):
            token.revoke()
            count += 1
        self.message_user(
            request,
            f'Revoked {count} token(s).',
            messages.SUCCESS if count else messages.WARNING,
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('user', 'name')
        return (
            'user',
            'name',
            'prefix',
            'key_hash',
            'created_at',
            'last_used_at',
            'revoked_at',
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields + ('user', 'name')

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return

        user = form.cleaned_data['user']
        name = form.cleaned_data.get('name') or 'MCP'
        if not is_agent_user(user):
            self.message_user(
                request,
                (
                    f'{user} is not in the Read Only (agent) group. '
                    'Token was still created, but MCP will reject it until they are.'
                ),
                messages.WARNING,
            )
        token, raw_key = AgentApiToken.create_token(user, name=name)
        obj.pk = token.pk
        obj.user = token.user
        obj.name = token.name
        obj.prefix = token.prefix
        obj.key_hash = token.key_hash
        obj.created_at = token.created_at
        obj.last_used_at = token.last_used_at
        obj.revoked_at = token.revoked_at
        self.message_user(
            request,
            (
                f'Token created for {user}. Copy it now — it will not be shown again: '
                f'{raw_key}'
            ),
            messages.SUCCESS,
        )
