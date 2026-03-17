from datetime import date, timedelta
from itertools import chain
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Count, DateField, OuterRef, Q, Subquery
from django.db.models import Value
from django.db.models.functions import Coalesce, Greatest, NullIf
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.contrib.auth import login, logout

from .forms import (
    CallLogForm,
    CoInvestmentForm,
    ContactForm,
    EmailLogForm,
    InfoLinkForm,
    InvestorAboutForm,
    InvestorForm,
    LoginForm,
    MeetingLogForm,
    OtherCommitmentForm,
    RegisterForm,
    ReminderForm,
)
from .models import (
    CallLog,
    CoInvestment,
    Contact,
    EmailLog,
    InfoLink,
    Investor,
    MeetingLog,
    Office,
    OtherCommitment,
    Reminder,
    Responsibility,
)
from django.contrib.auth.models import User


def _annotated_investors():
    latest_call = (
        CallLog.objects.filter(investor=OuterRef('pk'))
        .order_by('-date')
        .values('date')[:1]
    )
    latest_email = (
        EmailLog.objects.filter(investor=OuterRef('pk'))
        .order_by('-date')
        .values('date')[:1]
    )
    latest_coinvestment = (
        CoInvestment.objects.filter(
            investor=OuterRef('pk'), date__isnull=False
        )
        .order_by('-date')
        .values('date')[:1]
    )
    latest_meeting = (
        MeetingLog.objects.filter(investor=OuterRef('pk'))
        .order_by('-date')
        .values('date')[:1]
    )

    return Investor.objects.annotate(
        last_call=Subquery(latest_call, output_field=DateField()),
        last_email=Subquery(latest_email, output_field=DateField()),
        last_coinvestment=Subquery(
            latest_coinvestment, output_field=DateField()
        ),
        last_meeting=Subquery(latest_meeting, output_field=DateField()),
        latest_contact_date=NullIf(
            Greatest(
                Coalesce('last_call', date.min),
                Coalesce('last_email', date.min),
                Coalesce('last_coinvestment', date.min),
                Coalesce('last_meeting', date.min),
            ),
            Value(date.min, output_field=DateField()),
        ),
    ).select_related('responsibility', 'intermediary')


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'crm/accounts/register.html', {'form': form})


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email'].lower()
            password = form.cleaned_data['password']
            user = User.objects.filter(email=email).first()
            if user and user.check_password(password):
                login(request, user)
                next_url = request.GET.get('next', '/')
                return redirect(next_url)
            form.add_error(None, 'Invalid email or password.')
    else:
        form = LoginForm()
    return render(request, 'crm/accounts/login.html', {'form': form})


def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out and redirect to login. Accepts both GET and POST."""
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


def _reminder_qs():
    today = date.today()
    upcoming_cutoff = today + timedelta(days=7)
    return Reminder.objects.filter(
        is_done=False, due_date__lte=upcoming_cutoff
    ).select_related('investor')


@login_required
def investor_list(request: HttpRequest) -> HttpResponse:
    if request.method != 'GET':
        return HttpResponse(status=405)

    investors = _annotated_investors()

    search = request.GET.get('q', '').strip()
    status = request.GET.get('status') or ''
    responsibility_id = request.GET.get('responsibility') or ''
    sort = request.GET.get('sort') or 'name'
    default_sort_dir = 'desc' if sort == 'last_contacted' else 'asc'
    sort_dir = request.GET.get('sort_dir') or default_sort_dir

    if search:
        investors = investors.filter(
            Q(name__icontains=search)
            | Q(principal_contact__icontains=search)
            | Q(office__name__icontains=search)
        )
    if status:
        investors = investors.filter(status=status)
    if responsibility_id:
        investors = investors.filter(responsibility_id=responsibility_id)

    prefix = '' if sort_dir == 'asc' else '-'
    if sort == 'last_contacted':
        investors = investors.order_by(
            f'{prefix}latest_contact_date', 'name'
        )
    elif sort == 'principal':
        investors = investors.order_by(
            f'{prefix}principal_contact', 'name' if sort_dir == 'asc' else '-name'
        )
    elif sort == 'status':
        investors = investors.order_by(
            f'{prefix}status', 'name' if sort_dir == 'asc' else '-name'
        )
    elif sort == 'office':
        investors = investors.order_by(
            f'{prefix}office__name', 'name' if sort_dir == 'asc' else '-name'
        )
    elif sort == 'responsibility':
        investors = investors.order_by(
            f'{prefix}responsibility__name', 'name' if sort_dir == 'asc' else '-name'
        )
    else:
        investors = investors.order_by(
            f'{prefix}name'
        )

    stats = investors.aggregate(
        total=Count('id'),
        target_sma=Count('id', filter=Q(status='target_sma')),
        target_feeder_fund=Count('id', filter=Q(status='target_feeder_fund')),
        target_fund_iii=Count('id', filter=Q(status='target_fund_iii')),
        confirmed=Count('id', filter=Q(status='confirmed')),
        other=Count('id', filter=Q(status='other')),
    )

    responsibilities = Responsibility.objects.all()
    reminders = _reminder_qs()
    responsibility_choices = [('', 'All')] + [(r.id, r.name) for r in responsibilities]
    status_choices = [('', 'All')] + list(Investor.STATUS_CHOICES)

    filter_params = {}
    if search:
        filter_params['q'] = search
    if status:
        filter_params['status'] = status
    if responsibility_id:
        filter_params['responsibility'] = responsibility_id
    filter_params_str = urlencode(filter_params)

    context = {
        'investors': investors,
        'stats': stats,
        'responsibilities': responsibilities,
        'status_choices': status_choices,
        'responsibility_choices': responsibility_choices,
        'search': search,
        'status_filter': status,
        'responsibility_filter': responsibility_id,
        'sort': sort,
        'sort_dir': sort_dir,
        'filter_params_str': filter_params_str,
        'reminders': reminders,
    }
    is_htmx = (
        request.META.get('HTTP_HX_REQUEST') == 'true'
        or request.headers.get('HX-Request') == 'true'
    )
    if is_htmx:
        return render(request, 'crm/partials/investor_table.html', context)
    return render(request, 'crm/investor_list.html', context)


@login_required
def reminders_banner(request: HttpRequest) -> HttpResponse:
    reminders = _reminder_qs()
    return render(
        request,
        'crm/partials/reminders_banner.html',
        {'reminders': reminders},
    )


@login_required
def investor_detail(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(
        Investor.objects.select_related('responsibility', 'intermediary'),
        pk=pk,
    )

    reminders = investor.reminders.filter(is_done=False).order_by('due_date')
    contacts = investor.contacts.all()
    meeting_logs = investor.meeting_logs.all()
    call_logs = investor.call_logs.select_related('contact').all()
    email_logs = investor.email_logs.select_related('contact').all()
    co_investments = investor.co_investments.all()
    commitments = investor.commitments.all()
    info_links = investor.info_links.all()

    timeline_items = []
    for meeting in meeting_logs:
        pref = meeting.participants_display()
        inv = meeting.investor_participants_display(investor)
        parts = [p for p in (pref, inv) if p and p != '—']
        summary = f"Meeting ({', '.join(parts)})" if parts else "Meeting"
        timeline_items.append(
            {
                'date': meeting.date,
                'type': 'meeting',
                'summary': summary,
                'notes': meeting.notes,
            }
        )
    for call in call_logs:
        summary = f"Call with {call.with_display}" if call.with_display else "Call"
        timeline_items.append(
            {
                'date': call.date,
                'type': 'call',
                'summary': summary,
                'notes': call.notes,
            }
        )
    for email in email_logs:
        direction_word = 'Inbound' if email.direction == 'inbound' else 'Outbound'
        with_name = email.with_display or ''
        subject_part = f" — {email.subject}" if email.subject else ''
        prep = 'from' if email.direction == 'inbound' else 'to'
        summary = f"{direction_word} email {with_name and prep + ' ' + with_name}{subject_part}"
        timeline_items.append(
            {
                'date': email.date,
                'type': 'email',
                'summary': summary,
                'notes': email.notes,
            }
        )
    for coinvest in co_investments:
        summary = f'{coinvest.name} — {coinvest.get_decision_display()}'
        timeline_items.append(
            {
                'date': coinvest.date or date.min,
                'type': 'coinvestment',
                'summary': summary,
                'notes': '',
            }
        )

    timeline_items.sort(key=lambda item: item['date'], reverse=True)
    has_more = len(timeline_items) > 20
    timeline_display = timeline_items[:20]

    context = {
        'investor': investor,
        'reminders': reminders,
        'contacts': contacts,
        'meeting_logs': meeting_logs,
        'call_logs': call_logs,
        'email_logs': email_logs,
        'co_investments': co_investments,
        'commitments': commitments,
        'info_links': info_links,
        'timeline_items': timeline_display,
        'timeline_has_more': has_more,
    }
    return render(request, 'crm/investor_detail.html', context)


@login_required
def investor_create(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        form = InvestorForm(request.POST)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'investorListChanged'
            return response
    else:
        form = InvestorForm()
    return render(
        request,
        'crm/partials/investor_form_modal.html',
        {
            'form': form,
            'title': 'New Investor',
            'post_url': reverse('crm:investor_create'),
        },
    )


@login_required
def investor_edit(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = InvestorForm(request.POST, instance=investor)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'investorListChanged, investorDetailChanged'
            return response
    else:
        form = InvestorForm(instance=investor)
    return render(
        request,
        'crm/partials/investor_form_modal.html',
        {
            'form': form,
            'title': 'Edit Investor',
            'post_url': reverse('crm:investor_edit', args=[investor.pk]),
        },
    )


@login_required
def investor_about_edit(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = InvestorAboutForm(request.POST, instance=investor)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'investorDetailChanged'
            return response
    else:
        form = InvestorAboutForm(instance=investor)
    return render(
        request,
        'crm/partials/investor_about_form.html',
        {
            'form': form,
            'investor': investor,
            'post_url': reverse('crm:investor_about_edit', args=[investor.pk]),
        },
    )


@login_required
def investor_delete(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        investor.delete()
        response = HttpResponse('', content_type='text/html')
        response['HX-Trigger'] = 'investorListChanged'
        return response
    return render(
        request,
        'crm/partials/investor_delete_confirm.html',
        {
            'investor': investor,
            'delete_url': reverse('crm:investor_delete', args=[investor.pk]),
        },
    )


@login_required
def contact_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.investor = investor
            contact.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'contactsChanged'
            return response
    else:
        form = ContactForm()
    return render(
        request,
        'crm/partials/contact_form.html',
        {
            'form': form,
            'investor': investor,
            'post_url': reverse('crm:contact_create', args=[investor.pk]),
        },
    )


@login_required
def contact_delete(
    request: HttpRequest, pk: int, contact_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    contact = get_object_or_404(Contact, pk=contact_pk, investor=investor)
    if request.method == 'POST':
        contact.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'contactsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def calllog_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = CallLogForm(request.POST, investor=investor)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'callLogsChanged'
            return response
    else:
        form = CallLogForm(investor=investor)
    return render(
        request,
        'crm/partials/call_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:calllog_create', args=[investor.pk]),
        },
    )


@login_required
def calllog_edit(request: HttpRequest, pk: int, call_pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    call = get_object_or_404(CallLog, pk=call_pk, investor=investor)
    if request.method == 'POST':
        form = CallLogForm(request.POST, investor=investor, instance=call)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'callLogsChanged'
            return response
    else:
        form = CallLogForm(investor=investor, instance=call)
    return render(
        request,
        'crm/partials/call_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'title': 'Edit Call Log',
            'post_url': reverse('crm:calllog_edit', args=[investor.pk, call.pk]),
            'delete_url': reverse('crm:calllog_delete', args=[investor.pk, call.pk]),
        },
    )


@login_required
def calllog_delete(request: HttpRequest, pk: int, call_pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    call = get_object_or_404(CallLog, pk=call_pk, investor=investor)
    if request.method == 'POST':
        call.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'callLogsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def meetinglog_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = MeetingLogForm(request.POST, investor=investor)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'meetingLogsChanged'
            return response
    else:
        form = MeetingLogForm(investor=investor)
    return render(
        request,
        'crm/partials/meeting_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'title': 'Add Meeting Log',
            'post_url': reverse('crm:meetinglog_create', args=[investor.pk]),
        },
    )


@login_required
def meetinglog_edit(request: HttpRequest, pk: int, meeting_pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    meeting = get_object_or_404(MeetingLog, pk=meeting_pk, investor=investor)
    if request.method == 'POST':
        form = MeetingLogForm(request.POST, investor=investor, instance=meeting)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'meetingLogsChanged'
            return response
    else:
        form = MeetingLogForm(investor=investor, instance=meeting)
    return render(
        request,
        'crm/partials/meeting_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'title': 'Edit Meeting Log',
            'post_url': reverse('crm:meetinglog_edit', args=[investor.pk, meeting.pk]),
            'delete_url': reverse('crm:meetinglog_delete', args=[investor.pk, meeting.pk]),
        },
    )


@login_required
def meetinglog_delete(
    request: HttpRequest, pk: int, meeting_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    meeting = get_object_or_404(MeetingLog, pk=meeting_pk, investor=investor)
    if request.method == 'POST':
        meeting.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'meetingLogsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def emaillog_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = EmailLogForm(request.POST, investor=investor)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'emailLogsChanged'
            return response
    else:
        form = EmailLogForm(investor=investor)
    return render(
        request,
        'crm/partials/email_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:emaillog_create', args=[investor.pk]),
        },
    )


@login_required
def emaillog_edit(request: HttpRequest, pk: int, email_pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    email = get_object_or_404(EmailLog, pk=email_pk, investor=investor)
    if request.method == 'POST':
        form = EmailLogForm(request.POST, investor=investor, instance=email)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'emailLogsChanged'
            return response
    else:
        form = EmailLogForm(investor=investor, instance=email)
    return render(
        request,
        'crm/partials/email_log_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:emaillog_edit', args=[investor.pk, email.pk]),
            'delete_url': reverse('crm:emaillog_delete', args=[investor.pk, email.pk]),
        },
    )


@login_required
def emaillog_delete(
    request: HttpRequest, pk: int, email_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    email = get_object_or_404(EmailLog, pk=email_pk, investor=investor)
    if request.method == 'POST':
        email.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'emailLogsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def coinvestment_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = CoInvestmentForm(request.POST)
        if form.is_valid():
            coinvest = form.save(commit=False)
            coinvest.investor = investor
            coinvest.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'coinvestmentsChanged'
            return response
    else:
        form = CoInvestmentForm()
    return render(
        request,
        'crm/partials/co_investment_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:coinvestment_create', args=[investor.pk]),
        },
    )


@login_required
def coinvestment_edit(
    request: HttpRequest, pk: int, coinvest_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    coinvest = get_object_or_404(CoInvestment, pk=coinvest_pk, investor=investor)
    if request.method == 'POST':
        form = CoInvestmentForm(request.POST, instance=coinvest)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'coinvestmentsChanged'
            return response
    else:
        form = CoInvestmentForm(instance=coinvest)
    return render(
        request,
        'crm/partials/co_investment_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:coinvestment_edit', args=[investor.pk, coinvest.pk]),
            'delete_url': reverse('crm:coinvestment_delete', args=[investor.pk, coinvest.pk]),
        },
    )


@login_required
def coinvestment_delete(
    request: HttpRequest, pk: int, coinvest_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    coinvest = get_object_or_404(CoInvestment, pk=coinvest_pk, investor=investor)
    if request.method == 'POST':
        coinvest.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'coinvestmentsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def commitment_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = OtherCommitmentForm(request.POST)
        if form.is_valid():
            commitment = form.save(commit=False)
            commitment.investor = investor
            commitment.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'commitmentsChanged'
            return response
    else:
        form = OtherCommitmentForm()
    return render(
        request,
        'crm/partials/commitment_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:commitment_create', args=[investor.pk]),
        },
    )


@login_required
def commitment_edit(
    request: HttpRequest, pk: int, commit_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    commitment = get_object_or_404(
        OtherCommitment, pk=commit_pk, investor=investor
    )
    if request.method == 'POST':
        form = OtherCommitmentForm(request.POST, instance=commitment)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'commitmentsChanged'
            return response
    else:
        form = OtherCommitmentForm(instance=commitment)
    return render(
        request,
        'crm/partials/commitment_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:commitment_edit', args=[investor.pk, commitment.pk]),
        },
    )


@login_required
def commitment_delete(
    request: HttpRequest, pk: int, commit_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    commitment = get_object_or_404(
        OtherCommitment, pk=commit_pk, investor=investor
    )
    if request.method == 'POST':
        commitment.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'commitmentsChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def infolink_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = InfoLinkForm(request.POST)
        if form.is_valid():
            info = form.save(commit=False)
            info.investor = investor
            info.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'infoLinksChanged'
            return response
    else:
        form = InfoLinkForm()
    return render(
        request,
        'crm/partials/info_link_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:infolink_create', args=[investor.pk]),
        },
    )


@login_required
def infolink_edit(
    request: HttpRequest, pk: int, link_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    info = get_object_or_404(InfoLink, pk=link_pk, investor=investor)
    if request.method == 'POST':
        form = InfoLinkForm(request.POST, instance=info)
        if form.is_valid():
            form.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'infoLinksChanged'
            return response
    else:
        form = InfoLinkForm(instance=info)
    return render(
        request,
        'crm/partials/info_link_form.html',
        {
            'form': form,
            'investor': investor,
            'show_form': True,
            'post_url': reverse('crm:infolink_edit', args=[investor.pk, info.pk]),
        },
    )


@login_required
def infolink_delete(
    request: HttpRequest, pk: int, link_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    info = get_object_or_404(InfoLink, pk=link_pk, investor=investor)
    if request.method == 'POST':
        info.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'infoLinksChanged'
        return response
    return HttpResponseBadRequest('Invalid request')


@login_required
def reminder_create(request: HttpRequest, pk: int) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    if request.method == 'POST':
        form = ReminderForm(request.POST)
        if form.is_valid():
            reminder = form.save(commit=False)
            reminder.investor = investor
            reminder.save()
            response = HttpResponse('', content_type='text/html')
            response['HX-Trigger'] = 'remindersChanged'
            return response
    else:
        form = ReminderForm()
    return render(
        request,
        'crm/partials/reminder_form.html',
        {
            'form': form,
            'investor': investor,
            'post_url': reverse('crm:reminder_create', args=[investor.pk]),
        },
    )


@login_required
def reminder_done(
    request: HttpRequest, pk: int, reminder_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    reminder = get_object_or_404(Reminder, pk=reminder_pk, investor=investor)
    reminder.is_done = True
    reminder.save(update_fields=['is_done'])
    response = HttpResponse('', content_type='text/html')
    response['HX-Trigger'] = 'remindersChanged'
    return response


@login_required
def reminder_delete(
    request: HttpRequest, pk: int, reminder_pk: int
) -> HttpResponse:
    investor = get_object_or_404(Investor, pk=pk)
    reminder = get_object_or_404(Reminder, pk=reminder_pk, investor=investor)
    reminder.delete()
    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'remindersChanged'
    return response
