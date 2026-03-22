from datetime import date, timedelta
from itertools import chain
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, Count, DateField, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, Greatest, Least, NullIf
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
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
from .excel_import import import_workbook
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


INVESTORS_PER_PAGE = 100


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
    ).select_related('office', 'responsibility', 'intermediary')


def _apply_investor_list_filters(
    qs,
    *,
    search: str = '',
    type_filter: str = '',
    status: str = '',
    responsibility_id: str = '',
):
    """Same filters for dashboard stats (plain queryset) and table (annotated queryset)."""
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(principal_contact__icontains=search)
            | Q(office__name__icontains=search)
        )
    if type_filter:
        qs = qs.filter(type=type_filter)
    if status:
        qs = qs.filter(statuses__contains=[status])
    if responsibility_id:
        qs = qs.filter(responsibility_id=responsibility_id)
    return qs


def _order_investor_queryset(qs, sort: str, sort_dir: str):
    prefix = '' if sort_dir == 'asc' else '-'
    if sort == 'last_contacted':
        return qs.order_by(f'{prefix}latest_contact_date', 'name')
    if sort == 'principal':
        return qs.order_by(
            f'{prefix}principal_contact', 'name' if sort_dir == 'asc' else '-name'
        )
    if sort == 'type':
        return qs.order_by(f'{prefix}type', 'name' if sort_dir == 'asc' else '-name')
    if sort == 'status':
        return qs.order_by(f'{prefix}statuses', 'name' if sort_dir == 'asc' else '-name')
    if sort == 'office':
        return qs.order_by(
            f'{prefix}office__name', 'name' if sort_dir == 'asc' else '-name'
        )
    if sort == 'responsibility':
        return qs.order_by(
            f'{prefix}responsibility__name', 'name' if sort_dir == 'asc' else '-name'
        )
    # Default / Investor column: category priority (Target SMA → … → Revisit), then name
    z = Value(999, output_field=IntegerField())
    int_out = IntegerField()
    qs = qs.annotate(
        _sb0=Case(
            When(statuses__contains=['target_sma'], then=Value(0)),
            default=z,
            output_field=int_out,
        ),
        _sb1=Case(
            When(statuses__contains=['target_fund_iii'], then=Value(1)),
            default=z,
            output_field=int_out,
        ),
        _sb2=Case(
            When(statuses__contains=['target_feeder_fund'], then=Value(2)),
            default=z,
            output_field=int_out,
        ),
        _sb3=Case(
            When(statuses__contains=['confirmed_sma'], then=Value(3)),
            default=z,
            output_field=int_out,
        ),
        _sb4=Case(
            When(statuses__contains=['confirmed_fund_iii'], then=Value(4)),
            default=z,
            output_field=int_out,
        ),
        _sb5=Case(
            When(statuses__contains=['confirmed_feeder_fund'], then=Value(5)),
            default=z,
            output_field=int_out,
        ),
        _sb6=Case(
            When(statuses__contains=['other'], then=Value(6)),
            default=z,
            output_field=int_out,
        ),
        _sb7=Case(
            When(statuses__contains=['confirmed'], then=Value(7)),
            default=z,
            output_field=int_out,
        ),
    ).annotate(
        _status_bucket=Least(
            F('_sb0'),
            F('_sb1'),
            F('_sb2'),
            F('_sb3'),
            F('_sb4'),
            F('_sb5'),
            F('_sb6'),
            F('_sb7'),
        )
    )
    name_order = 'name' if sort_dir == 'asc' else '-name'
    return qs.order_by('_status_bucket', name_order)


def _investor_list_query_string(
    filter_params: dict,
    sort: str,
    sort_dir: str,
    *,
    page: int | None = None,
) -> str:
    """Build query string for list links, HTMX, and pagination (page omitted when 1)."""
    params = {**filter_params, 'sort': sort, 'sort_dir': sort_dir}
    if page is not None and page > 1:
        params['page'] = str(page)
    return urlencode(params)


def _investor_participant_labels(
    investor: Investor,
    participant_refs: list | None,
    contact_by_pk: dict[int, Contact],
) -> str:
    """Resolve meeting/call participant JSON without N+1 contact queries."""
    names: list[str] = []
    for p in participant_refs or []:
        if p == 'principal':
            if investor.principal_contact:
                names.append(investor.principal_contact)
        elif isinstance(p, str) and p.startswith('contact:'):
            try:
                cid = int(p.split(':', 1)[1])
            except (ValueError, IndexError):
                continue
            c = contact_by_pk.get(cid)
            if c:
                names.append(c.name)
    return ', '.join(names) if names else '—'


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

    search = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type') or ''
    status = request.GET.get('status') or ''
    responsibility_id = request.GET.get('responsibility') or ''
    sort = request.GET.get('sort') or 'name'
    default_sort_dir = 'desc' if sort == 'last_contacted' else 'asc'
    sort_dir = request.GET.get('sort_dir') or default_sort_dir

    is_htmx = (
        request.META.get('HTTP_HX_REQUEST') == 'true'
        or request.headers.get('HX-Request') == 'true'
    )

    filter_kwargs = dict(
        search=search,
        type_filter=type_filter,
        status=status,
        responsibility_id=responsibility_id,
    )

    investors_qs = _order_investor_queryset(
        _apply_investor_list_filters(
            _annotated_investors(),
            **filter_kwargs,
        ),
        sort,
        sort_dir,
    )

    filter_params = {}
    if search:
        filter_params['q'] = search
    if type_filter:
        filter_params['type'] = type_filter
    if status:
        filter_params['status'] = status
    if responsibility_id:
        filter_params['responsibility'] = responsibility_id
    filter_params_str = urlencode(filter_params)

    # Cheap total count (same filters, no subquery annotations)
    list_count_qs = _apply_investor_list_filters(
        Investor.objects.all(),
        **filter_kwargs,
    )
    paginator = Paginator(investors_qs, INVESTORS_PER_PAGE)
    # Avoid COUNT on the annotated queryset; Paginator.count is a cached_property.
    paginator.__dict__['count'] = list_count_qs.count()
    page_obj = paginator.get_page(request.GET.get('page'))
    investors = page_obj

    list_query_string = _investor_list_query_string(filter_params, sort, sort_dir)
    htmx_list_query_string = _investor_list_query_string(
        filter_params,
        sort,
        sort_dir,
        page=page_obj.number if page_obj.number > 1 else None,
    )

    if is_htmx:
        # Table-only: no stats aggregate, reminders, or choice lists.
        return render(
            request,
            'crm/partials/investor_table.html',
            {
                'investors': investors,
                'filter_params_str': filter_params_str,
                'list_query_string': list_query_string,
                'htmx_list_query_string': htmx_list_query_string,
                'sort': sort,
                'sort_dir': sort_dir,
                'page_obj': page_obj,
            },
        )

    # Full page: stats on a plain queryset (no last-contact subquery annotations)
    stats = list_count_qs.aggregate(
        target_sma=Count('id', filter=Q(statuses__contains=['target_sma'])),
        target_feeder_fund=Count('id', filter=Q(statuses__contains=['target_feeder_fund'])),
        target_fund_iii=Count('id', filter=Q(statuses__contains=['target_fund_iii'])),
        confirmed_sma=Count('id', filter=Q(statuses__contains=['confirmed_sma'])),
        confirmed_feeder_fund=Count(
            'id', filter=Q(statuses__contains=['confirmed_feeder_fund'])
        ),
        confirmed_fund_iii=Count(
            'id', filter=Q(statuses__contains=['confirmed_fund_iii'])
        ),
        other=Count('id', filter=Q(statuses__contains=['other'])),
        confirmed=Count('id', filter=Q(statuses__contains=['confirmed'])),
    )

    responsibilities = Responsibility.objects.all()
    reminders = _reminder_qs()
    responsibility_choices = [('', 'All')] + [(r.id, r.name) for r in responsibilities]
    type_choices = [('', 'All')] + list(Investor.TYPE_CHOICES)
    status_choices = [('', 'All')] + list(Investor.STATUS_CHOICES)

    context = {
        'investors': investors,
        'page_obj': page_obj,
        'stats': stats,
        'responsibilities': responsibilities,
        'type_choices': type_choices,
        'status_choices': status_choices,
        'responsibility_choices': responsibility_choices,
        'search': search,
        'type_filter': type_filter,
        'status_filter': status,
        'responsibility_filter': responsibility_id,
        'sort': sort,
        'sort_dir': sort_dir,
        'filter_params_str': filter_params_str,
        'list_query_string': list_query_string,
        'htmx_list_query_string': htmx_list_query_string,
        'reminders': reminders,
    }
    return render(request, 'crm/investor_list.html', context)


@login_required
def investor_import(request: HttpRequest) -> HttpResponse:
    """Upload .xlsx to create/update investors from spreadsheet columns."""
    result = None
    if request.method == 'POST':
        f = request.FILES.get('file')
        if not f:
            messages.error(request, 'Please choose an Excel file (.xlsx).')
        elif not f.name.lower().endswith('.xlsx'):
            messages.error(request, 'Please upload an .xlsx file (Excel).')
        else:
            try:
                result = import_workbook(f)
                skipped = result.get('skipped_duplicates', 0)
                skip_msg = f', {skipped} duplicate row(s) skipped in file' if skipped else ''
                messages.success(
                    request,
                    f'Import finished: {result["created"]} created, '
                    f'{result["updated"]} updated, '
                    f'{result["rows_failed"]} row(s) failed{skip_msg}.',
                )
            except Exception as exc:
                messages.error(request, f'Could not read file: {exc}')
    return render(
        request,
        'crm/investor_import.html',
        {'result': result},
    )


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
        _annotated_investors()
        .filter(pk=pk)
        .prefetch_related(
            Prefetch(
                'reminders',
                queryset=Reminder.objects.filter(is_done=False).order_by('due_date'),
                to_attr='open_reminders',
            ),
            'contacts',
            'meeting_logs',
            Prefetch(
                'call_logs',
                queryset=CallLog.objects.select_related('contact'),
            ),
            Prefetch(
                'email_logs',
                queryset=EmailLog.objects.select_related('contact'),
            ),
            'co_investments',
            'commitments',
            'info_links',
        ),
        pk=pk,
    )

    reminders = investor.open_reminders
    contacts = list(investor.contacts.all())
    contact_by_pk = {c.pk: c for c in contacts}
    meeting_logs = list(investor.meeting_logs.all())
    call_logs = list(investor.call_logs.all())
    email_logs = list(investor.email_logs.all())

    for meeting in meeting_logs:
        meeting.inv_participants_label = _investor_participant_labels(
            investor, meeting.investor_participants, contact_by_pk
        )
    for call in call_logs:
        if call.investor_participants:
            wd = _investor_participant_labels(
                investor, call.investor_participants, contact_by_pk
            )
            call.inv_with_display = wd if wd != '—' else ''
        elif call.contact_id:
            c = contact_by_pk.get(call.contact_id) or call.contact
            call.inv_with_display = (
                c.name if c else (call.contact_name_override or '')
            )
        else:
            call.inv_with_display = call.contact_name_override or ''
    co_investments = list(investor.co_investments.all())
    commitments = list(investor.commitments.all())
    info_links = list(investor.info_links.all())

    timeline_items = []
    for meeting in meeting_logs:
        pref = meeting.participants_display()
        inv = _investor_participant_labels(
            investor, meeting.investor_participants, contact_by_pk
        )
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
        if call.investor_participants:
            wd = _investor_participant_labels(
                investor, call.investor_participants, contact_by_pk
            )
            summary = (
                f"Call with {wd}"
                if wd != '—'
                else "Call"
            )
        elif call.contact_id:
            c = contact_by_pk.get(call.contact_id) or call.contact
            summary = f"Call with {c.name}" if c else "Call"
        else:
            summary = (
                f"Call with {call.contact_name_override}"
                if call.contact_name_override
                else "Call"
            )
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
