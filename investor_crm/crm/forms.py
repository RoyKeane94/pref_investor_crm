from collections import OrderedDict
from typing import Any, Iterable, Tuple

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

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
    PARTICIPANT_CHOICES,
    Reminder,
    Responsibility,
)


class TailwindFormMixin:
    input_class = 'w-full border border-grey-border rounded-card px-3 py-2 text-body-sm bg-white text-navy focus:outline-none focus:ring-1 focus:ring-accent'
    textarea_class = 'w-full border border-grey-border rounded-card px-3 py-2 text-body-sm bg-white text-navy focus:outline-none focus:ring-1 focus:ring-accent'
    select_class = 'w-full border border-grey-border rounded-card px-3 py-2 text-body-sm bg-white text-navy focus:outline-none focus:ring-1 focus:ring-accent'
    checkbox_class = 'rounded border-grey-border text-accent'

    def _apply_tailwind_styles(self) -> None:
        for field in self.fields.values():
            widget = field.widget
            existing = widget.attrs.get('class', '')

            def _add(cls: str) -> None:
                widget.attrs['class'] = (existing + ' ' + cls).strip()

            if isinstance(
                widget,
                (
                    forms.TextInput,
                    forms.EmailInput,
                    forms.PasswordInput,
                    forms.URLInput,
                    forms.NumberInput,
                    forms.DateInput,
                ),
            ):
                _add(self.input_class)
            elif isinstance(widget, forms.Textarea):
                _add(self.textarea_class)
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                _add(self.select_class)
            elif isinstance(widget, forms.CheckboxInput):
                _add(self.checkbox_class)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._apply_tailwind_styles()


class RegisterForm(TailwindFormMixin, UserCreationForm):
    """Registration with email and password only. Username is set to email internally."""

    class Meta:
        model = User
        fields = ['email', 'password1', 'password2']

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True
        self.fields['password1'].help_text = None
        self.fields['password2'].help_text = None

    def clean_email(self) -> str:
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit: bool = True) -> User:
        email = self.cleaned_data['email'].lower()
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data['password1'],
        )
        return user


class LoginForm(TailwindFormMixin, forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Password', widget=forms.PasswordInput)


class InvestorForm(TailwindFormMixin, forms.ModelForm):
    intermediary_name = forms.CharField(
        required=False, label='New intermediary name (if not in list)'
    )
    statuses = forms.MultipleChoiceField(
        label='Status',
        choices=Investor.STATUS_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Investor
        fields = [
            'name',
            'principal_contact',
            'website',
            'type',
            'ticket_size',
            'vdr_access',
            'vdr_access_date',
            'meeting',
            'office',
            'responsibility',
            'prefequity_owner',
            'intermediary',
        ]
        labels = {
            'ticket_size': 'Typical Ticket Size',
        }
        widgets = {
            'ticket_size': forms.NumberInput(attrs={'step': '0.1'}),
            'vdr_access_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        office_name = forms.CharField(
            required=False,
            label='New office name (if not in list)',
        )
        office_name.widget.attrs['class'] = self.input_class
        new_fields = OrderedDict()
        for name, field in self.fields.items():
            new_fields[name] = field
            if name == 'office':
                new_fields['office_name'] = office_name
        self.fields = new_fields
        self.fields['prefequity_owner'].required = False
        self.fields['prefequity_owner'].label = 'Prefequity Owner'
        if self.instance and self.instance.pk and self.instance.statuses:
            self.initial['statuses'] = self.instance.statuses

    def clean(self):
        cleaned = super().clean()
        responsibility = cleaned.get('responsibility')
        intermediary = cleaned.get('intermediary')
        intermediary_name = cleaned.get('intermediary_name')

        if responsibility and responsibility.name == 'Intermediary':
            if not intermediary and not intermediary_name:
                self.add_error(
                    'intermediary',
                    'Please select an intermediary or enter a new one.',
                )
        return cleaned

    def save(self, commit: bool = True) -> Investor:
        instance: Investor = super().save(commit=False)
        responsibility: Responsibility | None = self.cleaned_data.get(
            'responsibility'
        )
        intermediary: Intermediary | None = self.cleaned_data.get('intermediary')
        intermediary_name: str = self.cleaned_data.get('intermediary_name') or ''
        office_name: str = self.cleaned_data.get('office_name') or ''

        if responsibility and responsibility.name == 'Intermediary':
            if not intermediary and (intermediary_name or '').strip():
                intermediary, _ = Intermediary.objects.get_or_create(
                    name=(intermediary_name or '').strip()
                )
            instance.intermediary = intermediary
        else:
            instance.intermediary = None

        if (office_name or '').strip():
            office, _ = Office.objects.get_or_create(
                name=(office_name or '').strip()
            )
            instance.office = office

        statuses = self.cleaned_data.get('statuses') or []
        instance.statuses = list(statuses) if statuses else (['target_fund_iii'] if not instance.pk else [])
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class InvestorAboutForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Investor
        fields = ['about']


class ContactForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name']


def _with_choices_for_investor(investor: Investor) -> Iterable[Tuple[str, str]]:
    choices: list[Tuple[str, str]] = []
    if investor.principal_contact:
        choices.append(('principal', investor.principal_contact))
    for contact in investor.contacts.all():
        choices.append((f'contact:{contact.pk}', contact.name))
    return choices


class MeetingLogForm(TailwindFormMixin, forms.ModelForm):
    participants = forms.MultipleChoiceField(
        label='Prefequity participants',
        choices=PARTICIPANT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    investor_participants = forms.MultipleChoiceField(
        label='Investor participants',
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = MeetingLog
        fields = ['date', 'participants', 'investor_participants', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, investor: Investor, **kwargs: Any) -> None:
        self.investor = investor
        super().__init__(*args, **kwargs)
        self.fields['investor_participants'].choices = list(
            _with_choices_for_investor(investor)
        )
        if self.instance and self.instance.pk:
            if self.instance.participants:
                self.initial['participants'] = self.instance.participants
            if self.instance.investor_participants:
                self.initial['investor_participants'] = self.instance.investor_participants

    def save(self, commit: bool = True) -> MeetingLog:
        instance: MeetingLog = super().save(commit=False)
        instance.investor = self.investor
        instance.participants = self.cleaned_data.get('participants') or []
        instance.investor_participants = (
            self.cleaned_data.get('investor_participants') or []
        )
        if commit:
            instance.save()
        return instance


class CallLogForm(TailwindFormMixin, forms.ModelForm):
    participants = forms.MultipleChoiceField(
        label='Prefequity participants',
        choices=PARTICIPANT_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    investor_participants = forms.MultipleChoiceField(
        label='Investor participants',
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = CallLog
        fields = ['date', 'participants', 'investor_participants', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, investor: Investor, **kwargs: Any) -> None:
        self.investor = investor
        super().__init__(*args, **kwargs)
        self.fields['investor_participants'].choices = list(
            _with_choices_for_investor(investor)
        )
        if self.instance and self.instance.pk:
            if self.instance.participants:
                self.initial['participants'] = self.instance.participants
            if self.instance.investor_participants:
                self.initial['investor_participants'] = (
                    self.instance.investor_participants
                )
            elif self.instance.contact or self.instance.contact_name_override:
                # Migrate from old single contact
                if self.instance.contact:
                    self.initial['investor_participants'] = [
                        f'contact:{self.instance.contact.pk}'
                    ]
                else:
                    self.initial['investor_participants'] = ['principal']

    def save(self, commit: bool = True) -> CallLog:
        instance: CallLog = super().save(commit=False)
        instance.investor = self.investor
        instance.participants = self.cleaned_data.get('participants') or []
        instance.investor_participants = (
            self.cleaned_data.get('investor_participants') or []
        )
        instance.contact = None
        instance.contact_name_override = ''
        if commit:
            instance.save()
        return instance


class EmailLogForm(TailwindFormMixin, forms.ModelForm):
    with_person = forms.ChoiceField(label='With')

    class Meta:
        model = EmailLog
        fields = ['date', 'with_person', 'subject', 'direction', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, investor: Investor, **kwargs: Any) -> None:
        self.investor = investor
        super().__init__(*args, **kwargs)
        self.fields['with_person'].choices = _with_choices_for_investor(investor)

    def save(self, commit: bool = True) -> EmailLog:
        instance: EmailLog = super().save(commit=False)
        instance.investor = self.investor
        choice = self.cleaned_data.get('with_person')
        instance.contact = None
        instance.contact_name_override = ''
        if choice == 'principal':
            instance.contact_name_override = self.investor.principal_contact
        elif choice and choice.startswith('contact:'):
            contact_id = choice.split(':', 1)[1]
            try:
                instance.contact = self.investor.contacts.get(pk=contact_id)
            except Contact.DoesNotExist:
                instance.contact = None
        if commit:
            instance.save()
        return instance


class CoInvestmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CoInvestment
        fields = ['name', 'size', 'decision', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }


class OtherCommitmentForm(TailwindFormMixin, forms.ModelForm):
    year = forms.IntegerField(
        label='Year',
        required=False,
        min_value=1900,
        max_value=2100,
        widget=forms.NumberInput(attrs={'placeholder': 'e.g. 2024'}),
    )

    class Meta:
        model = OtherCommitment
        fields = ['fund', 'amount', 'notes']
        exclude = ['date']
        field_order = ['fund', 'amount', 'year', 'notes']

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.date:
            self.initial['year'] = self.instance.date.year

    def save(self, commit: bool = True) -> OtherCommitment:
        instance: OtherCommitment = super().save(commit=False)
        year = self.cleaned_data.get('year')
        if year:
            from datetime import date
            instance.date = date(year, 1, 1)
        else:
            instance.date = None
        if commit:
            instance.save()
        return instance


class InfoLinkForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = InfoLink
        fields = ['title', 'detail', 'link']


class ReminderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Reminder
        fields = ['description', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
