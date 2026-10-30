import hashlib
import secrets
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone


class Responsibility(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class Intermediary(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class Office(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.name


class Investor(models.Model):
    STATUS_CHOICES = [
        ('target_sma', 'Target for SMA'),
        ('target_feeder_fund', 'Target for Feeder'),
        ('target_fund_iii', 'Target for Fund III'),
        ('confirmed_sma', 'Confirmed for SMA'),
        ('confirmed_feeder_fund', 'Confirmed for Feeder'),
        ('confirmed_fund_iii', 'Confirmed for Fund III'),
        ('other', 'Other'),
        ('confirmed', 'Revisit'),
        ('dead', 'Dead'),
    ]

    TYPE_CHOICES = [
        ('asset_manager', 'Asset manager'),
        ('bank', 'Bank'),
        ('endowment_charity', 'Endowment/charity'),
        ('fund_manager', 'Fund manager'),
        ('fund_of_funds', 'Fund of funds'),
        ('gatekeeper_consultant', 'Gatekeeper/consultant'),
        ('hnw_uhnw', 'HNW/UHNW'),
        ('insurance_company', 'Insurance company'),
        ('investment_company_trust', 'Investment company/trust'),
        ('pension_fund_company', 'Pension fund/company'),
        ('lgps', 'LGPS'),
        ('lgps_pool', 'LGPS pool'),
        ('single_family_office', 'Single family office'),
        ('swf_government', 'SWF/government'),
        ('wealth_manager_pb_mfo', 'Wealth manager/PB/MFO'),
    ]

    name = models.CharField(max_length=255)
    principal_contact = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    statuses = models.JSONField(
        default=list,
        blank=True,
        help_text='List of status values (target_sma, target_feeder_fund, etc.)',
    )
    type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        blank=True,
        default='',
    )
    ticket_size = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text='Ticket size in £m',
    )
    vdr_access = models.BooleanField(default=False)
    vdr_access_date = models.DateField(null=True, blank=True)
    meeting = models.BooleanField(default=False)
    about = models.TextField(blank=True)
    office = models.ForeignKey(
        'Office',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='investors',
    )
    responsibility = models.ForeignKey(
        Responsibility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    intermediary = models.ForeignKey(
        Intermediary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    prefequity_owner = models.CharField(
        max_length=10,
        choices=[
            ('TD', 'TD'),
            ('NP', 'NP'),
            ('JCP', 'JCP'),
            ('TB', 'TB'),
            ('PW', 'PW'),
        ],
        blank=True,
        default='',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @property
    def last_contacted(self):
        """Return the most recent date from call_logs, email_logs, co_investments or meeting_logs, or None."""
        from itertools import chain

        dates = list(
            chain(
                self.call_logs.values_list('date', flat=True),
                self.email_logs.values_list('date', flat=True),
                self.co_investments.exclude(date__isnull=True).values_list(
                    'date', flat=True
                ),
                self.meeting_logs.values_list('date', flat=True),
            )
        )
        return max(dates) if dates else None


class Contact(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='contacts'
    )
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_ex = models.BooleanField(
        default=False,
        help_text='Former contact; hidden from active contact pickers.',
    )

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


PARTICIPANT_CHOICES = [
    ('TD', 'TD'),
    ('NP', 'NP'),
    ('JCP', 'JCP'),
    ('TB', 'TB'),
    ('PW', 'PW'),
]


class MeetingLog(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='meeting_logs'
    )
    date = models.DateField()
    participants = models.JSONField(
        default=list,
        blank=True,
        help_text='Prefequity participants (TD, NP, JCP, TB, PW)',
    )
    investor_participants = models.JSONField(
        default=list,
        blank=True,
        help_text='Investor participants: principal, contact:pk',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def participants_display(self) -> str:
        """Return comma-separated participant codes."""
        return ', '.join(self.participants) if self.participants else '—'

    def investor_participants_display(self, investor: 'Investor') -> str:
        """Return comma-separated investor participant names."""
        names = []
        for p in self.investor_participants or []:
            if p == 'principal':
                if investor.principal_contact:
                    names.append(investor.principal_contact)
            elif isinstance(p, str) and p.startswith('contact:'):
                try:
                    cid = int(p.split(':', 1)[1])
                    c = investor.contacts.filter(pk=cid).first()
                    if c:
                        names.append(c.name)
                except (ValueError, IndexError):
                    pass
        return ', '.join(names) if names else '—'


class CallLog(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='call_logs'
    )
    date = models.DateField()
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True
    )
    contact_name_override = models.CharField(max_length=255, blank=True)
    participants = models.JSONField(
        default=list,
        blank=True,
        help_text='Prefequity participants (TD, NP, JCP, TB, PW)',
    )
    investor_participants = models.JSONField(
        default=list,
        blank=True,
        help_text='Investor participants: principal, contact:pk',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    @property
    def with_display(self) -> str:
        if self.investor_participants:
            return self._investor_participants_display()
        if self.contact:
            return self.contact.name
        return self.contact_name_override or ''

    def _investor_participants_display(self) -> str:
        names = []
        for p in self.investor_participants or []:
            if p == 'principal':
                if self.investor.principal_contact:
                    names.append(self.investor.principal_contact)
            elif isinstance(p, str) and p.startswith('contact:'):
                try:
                    cid = int(p.split(':', 1)[1])
                    c = self.investor.contacts.filter(pk=cid).first()
                    if c:
                        names.append(c.name)
                except (ValueError, IndexError):
                    pass
        return ', '.join(names) if names else ''

    def investor_participants_display(self, investor=None) -> str:
        """Return comma-separated investor participant names (for template filter)."""
        return self._investor_participants_display()


class EmailLog(models.Model):
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]

    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='email_logs'
    )
    date = models.DateField()
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True
    )
    contact_name_override = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    @property
    def with_display(self) -> str:
        if self.contact:
            return self.contact.name
        return self.contact_name_override or ''


class OtherCommitment(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='commitments'
    )
    fund = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=10, decimal_places=1, null=True, blank=True
    )
    date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)


class InfoLink(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='info_links'
    )
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    link = models.URLField(blank=True)


class CoInvestment(models.Model):
    DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('committed', 'Committed'),
        ('passed', 'Passed'),
    ]

    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='co_investments'
    )
    name = models.CharField(max_length=255)
    size = models.DecimalField(
        max_digits=10, decimal_places=1, null=True, blank=True
    )
    decision = models.CharField(
        max_length=10, choices=DECISION_CHOICES, default='pending'
    )
    date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-date']


class Reminder(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='reminders'
    )
    description = models.CharField(max_length=500)
    due_date = models.DateField()
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date']

    @property
    def is_overdue(self) -> bool:
        return not self.is_done and self.due_date < date.today()


class AgentNote(models.Model):
    """Findings logged by agent accounts for team review."""

    NOTE_TYPE_CHOICES = [
        ('news', 'News'),
        ('person_change', 'Personnel change'),
        ('investment', 'Investment'),
        ('flag', 'Flag for review'),
        ('fit_flag', 'Fit flag'),
        ('checked', 'Checked'),
        ('note', 'Note'),
    ]
    CONFIDENCE_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='agent_notes'
    )
    author = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_notes',
    )
    note_type = models.CharField(
        max_length=20, choices=NOTE_TYPE_CHOICES, default='news'
    )
    title = models.CharField(
        max_length=500,
        blank=True,
        help_text='Headline or short label',
    )
    body = models.TextField(
        blank=True,
        help_text='Summary / detail',
    )
    link = models.URLField(
        blank=True,
        help_text='Source URL (news article, press release, etc.)',
    )
    person_name = models.CharField(max_length=255, blank=True)
    moved_from = models.CharField(
        max_length=255, blank=True, help_text='Previous role / organisation'
    )
    moved_to = models.CharField(
        max_length=255, blank=True, help_text='New role / organisation'
    )
    event_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date of the source event (article, change, investment, etc.), if known',
    )
    confidence = models.CharField(
        max_length=10,
        choices=CONFIDENCE_CHOICES,
        blank=True,
        default='',
        help_text='How confident the agent is in this finding',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.get_note_type_display()} · {self.investor.name}'

    @property
    def display_summary(self) -> str:
        if self.note_type == 'person_change':
            name = (self.person_name or '').strip() or 'Unknown'
            frm = (self.moved_from or '').strip() or '—'
            to = (self.moved_to or '').strip() or '—'
            return f'{name}: {frm} → {to}'
        if self.note_type in ('flag', 'fit_flag'):
            return (
                (self.title or '').strip()
                or (self.body or '').strip()
                or ('Fit' if self.note_type == 'fit_flag' else 'Needs review')
            )
        if self.note_type == 'checked':
            return (
                (self.title or '').strip()
                or (self.body or '').strip()
                or 'Checked'
            )
        if self.note_type == 'note':
            return (self.body or '').strip() or (self.title or '').strip() or '—'
        return (self.title or '').strip() or (self.body or '').strip() or '—'


class AgentApiToken(models.Model):
    """Bearer token for agent MCP access. Store only a hash; show the raw key once."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_api_tokens',
    )
    name = models.CharField(max_length=100, default='MCP')
    prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        status = 'revoked' if self.revoked_at else 'active'
        return f'{self.name} ({self.prefix}…) · {self.user} · {status}'

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    @classmethod
    def create_token(cls, user, name: str = 'MCP') -> tuple['AgentApiToken', str]:
        raw_key = 'agt_' + secrets.token_urlsafe(32)
        token = cls.objects.create(
            user=user,
            name=name,
            prefix=raw_key[:12],
            key_hash=cls.hash_key(raw_key),
        )
        return token, raw_key

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=['revoked_at'])

    def mark_used(self) -> None:
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])
