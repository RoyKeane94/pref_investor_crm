from datetime import date

from django.db import models


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
        ('confirmed', 'Confirmed'),
        ('potential_sma', 'Potential SMA'),
        ('target_fund_iii', 'Target for Fund III'),
    ]

    name = models.CharField(max_length=255)
    principal_contact = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='target_fund_iii',
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    @property
    def last_contacted(self):
        """Return the most recent date from call_logs, email_logs or co_investments, or None."""
        from itertools import chain

        dates = list(
            chain(
                self.call_logs.values_list('date', flat=True),
                self.email_logs.values_list('date', flat=True),
                self.co_investments.exclude(date__isnull=True).values_list(
                    'date', flat=True
                ),
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

    def __str__(self) -> str:
        return self.name


class CallLog(models.Model):
    investor = models.ForeignKey(
        Investor, on_delete=models.CASCADE, related_name='call_logs'
    )
    date = models.DateField()
    contact = models.ForeignKey(
        Contact, on_delete=models.SET_NULL, null=True, blank=True
    )
    contact_name_override = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    @property
    def with_display(self) -> str:
        if self.contact:
            return self.contact.name
        return self.contact_name_override or ''


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
