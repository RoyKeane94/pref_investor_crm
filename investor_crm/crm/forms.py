from collections import OrderedDict
from typing import Any, Iterable, Tuple

from django import forms

from .models import (
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

        # Keep the Office dropdown options in alphabetical order.
        # (Office model itself doesn't define a default ordering.)
        if 'office' in self.fields:
            self.fields['office'].queryset = Office.objects.all().order_by('name')

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
    for contact in investor.contacts.filter(is_ex=False):
        choices.append((f'contact:{contact.pk}', contact.name))
    return choices


class MarkExContactForm(TailwindFormMixin, forms.Form):
    """Move the principal or an other contact into Ex Contacts."""

    person = forms.ChoiceField(label='Contact')
    replacement = forms.ChoiceField(
        label='New principal contact',
        required=False,
    )

    def __init__(self, *args: Any, investor: Investor, **kwargs: Any) -> None:
        self.investor = investor
        super().__init__(*args, **kwargs)
        active = list(investor.contacts.filter(is_ex=False))
        person_choices: list[Tuple[str, str]] = [('', 'Select...')]
        if investor.principal_contact:
            person_choices.append(
                ('principal', f'{investor.principal_contact} (principal)')
            )
        for contact in active:
            person_choices.append((f'contact:{contact.pk}', contact.name))
        self.fields['person'].choices = person_choices

        replacement_choices: list[Tuple[str, str]] = [('', 'Select...')]
        for contact in active:
            replacement_choices.append((f'contact:{contact.pk}', contact.name))
        self.fields['replacement'].choices = replacement_choices

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        person = cleaned.get('person') or ''
        replacement = cleaned.get('replacement') or ''
        if person == 'principal':
            if not replacement:
                self.add_error(
                    'replacement',
                    'Choose a replacement principal contact before marking '
                    'the current principal as an ex contact.',
                )
            elif not self.investor.contacts.filter(
                is_ex=False, pk=replacement.split(':', 1)[-1]
            ).exists():
                self.add_error(
                    'replacement',
                    'Add another contact first, then choose them as the new principal.',
                )
            elif replacement == 'principal':
                self.add_error('replacement', 'Choose a different contact.')
        return cleaned

    def save(self) -> None:
        person = self.cleaned_data['person']
        if person == 'principal':
            old_name = (self.investor.principal_contact or '').strip()
            replacement = self.cleaned_data['replacement']
            contact_id = replacement.split(':', 1)[1]
            new_principal = self.investor.contacts.get(pk=contact_id, is_ex=False)
            if old_name:
                existing_ex = self.investor.contacts.filter(
                    name=old_name, is_ex=True
                ).first()
                if not existing_ex:
                    Contact.objects.create(
                        investor=self.investor,
                        name=old_name,
                        is_ex=True,
                    )
            self.investor.principal_contact = new_principal.name
            self.investor.save(update_fields=['principal_contact', 'updated_at'])
            # Promoted contact becomes the principal, not an "other" contact.
            new_principal.delete()
            return

        if person.startswith('contact:'):
            contact_id = person.split(':', 1)[1]
            contact = self.investor.contacts.get(pk=contact_id, is_ex=False)
            contact.is_ex = True
            contact.save(update_fields=['is_ex'])


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
    with_person = forms.ChoiceField(label='To/From')

    class Meta:
        model = EmailLog
        fields = ['date', 'with_person', 'subject', 'direction', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, investor: Investor, **kwargs: Any) -> None:
        self.investor = investor
        super().__init__(*args, **kwargs)
        self.fields['with_person'].choices = [
            ('', 'Select...'),
            *_with_choices_for_investor(investor),
        ]
        if self.instance and self.instance.pk:
            if self.instance.contact_id:
                self.initial['with_person'] = f'contact:{self.instance.contact_id}'
            elif self.instance.contact_name_override:
                override = self.instance.contact_name_override
                if override == self.investor.principal_contact:
                    self.initial['with_person'] = 'principal'
                else:
                    # Contact may have been deleted; keep the submitted name selectable.
                    orphan_value = f'name:{override}'
                    self.fields['with_person'].choices = [
                        ('', 'Select...'),
                        (orphan_value, override),
                        *_with_choices_for_investor(investor),
                    ]
                    self.initial['with_person'] = orphan_value
            else:
                self.initial['with_person'] = ''

    def save(self, commit: bool = True) -> EmailLog:
        instance: EmailLog = super().save(commit=False)
        instance.investor = self.investor
        choice = self.cleaned_data.get('with_person') or ''
        instance.contact = None
        # Always denormalize the name so To/From survives contact deletion.
        choice_labels = dict(self.fields['with_person'].choices)
        display_name = (choice_labels.get(choice) or '').strip()
        if choice == 'principal':
            instance.contact_name_override = (
                (self.investor.principal_contact or '').strip() or display_name
            )
        elif choice.startswith('contact:'):
            contact_id = choice.split(':', 1)[1]
            try:
                instance.contact = self.investor.contacts.get(pk=contact_id)
            except (Contact.DoesNotExist, ValueError):
                instance.contact = None
            instance.contact_name_override = (
                instance.contact.name if instance.contact else display_name
            )
        elif choice.startswith('name:'):
            instance.contact_name_override = choice.split(':', 1)[1].strip() or display_name
        else:
            instance.contact_name_override = display_name
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


class AgentNoteForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = AgentNote
        fields = [
            'investor',
            'note_type',
            'title',
            'body',
            'link',
            'person_name',
            'moved_from',
            'moved_to',
            'event_date',
            'confidence',
        ]
        labels = {
            'note_type': 'Type',
            'title': 'Headline / label',
            'body': 'Detail',
            'link': 'Source link',
            'person_name': 'Person',
            'moved_from': 'From',
            'moved_to': 'To',
            'event_date': 'Event date',
            'confidence': 'Confidence',
        }
        widgets = {
            'body': forms.Textarea(attrs={'rows': 3}),
            'link': forms.URLInput(attrs={'placeholder': 'https://…'}),
            'event_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['investor'].queryset = Investor.objects.order_by('name')
        self.fields['investor'].empty_label = 'Select investor…'
        for name in (
            'title',
            'body',
            'link',
            'person_name',
            'moved_from',
            'moved_to',
            'event_date',
            'confidence',
        ):
            self.fields[name].required = False
        self.fields['moved_from'].widget.attrs['placeholder'] = (
            'Previous role / organisation'
        )
        self.fields['moved_to'].widget.attrs['placeholder'] = (
            'New role / organisation'
        )
        self.fields['title'].widget.attrs['placeholder'] = (
            'e.g. Appoints new CIO / Commits to Fund X'
        )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        note_type = cleaned.get('note_type')
        if note_type == 'person_change':
            if not (cleaned.get('person_name') or '').strip():
                self.add_error('person_name', 'Enter the person’s name.')
        elif note_type == 'news':
            if not (cleaned.get('title') or '').strip() and not (
                cleaned.get('body') or ''
            ).strip():
                self.add_error('title', 'Enter a headline or detail for the news.')
            if not (cleaned.get('link') or '').strip():
                self.add_error('link', 'Include a source link for news.')
        elif note_type == 'investment':
            if not (cleaned.get('title') or '').strip() and not (
                cleaned.get('body') or ''
            ).strip():
                self.add_error(
                    'title', 'Enter a label or detail for the investment.'
                )
        return cleaned
