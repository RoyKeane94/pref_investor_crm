"""Serialize CRM models for MCP tool responses."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from crm.models import AgentNote, Contact, Investor


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _dec(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def serialize_investor_summary(investor: Investor) -> dict[str, Any]:
    return {
        'id': investor.pk,
        'name': investor.name,
        'statuses': list(investor.statuses or []),
        'type': investor.type or '',
        'principal_contact': investor.principal_contact or '',
        'website': investor.website or '',
        'ticket_size_m': _dec(investor.ticket_size),
        'office': investor.office.name if investor.office_id else None,
        'last_contacted': _iso(investor.last_contacted),
    }


def serialize_contact(contact: Contact) -> dict[str, Any]:
    return {
        'id': contact.pk,
        'name': contact.name,
        'role': contact.role or '',
        'title': contact.role or '',
        'email': contact.email or '',
        'phone': contact.phone or '',
        'is_ex': contact.is_ex,
    }


def serialize_finding(note: AgentNote) -> dict[str, Any]:
    return {
        'id': note.pk,
        'investor_id': note.investor_id,
        'investor_name': note.investor.name if note.investor_id else None,
        'type': note.note_type,
        'headline': note.title or '',
        'detail': note.body or '',
        'source_url': note.link or '',
        'event_date': _iso(note.event_date),
        'logged_date': (
            note.created_at.date().isoformat() if note.created_at else None
        ),
        'confidence': note.confidence or '',
        'person': note.person_name or '',
        'from': note.moved_from or '',
        'to': note.moved_to or '',
        'author_id': note.author_id,
        'author_email': (
            (note.author.email or note.author.username) if note.author_id else None
        ),
        'created_at': _iso(note.created_at),
        'updated_at': _iso(note.updated_at),
    }


def serialize_investor_detail(investor: Investor) -> dict[str, Any]:
    contacts = [
        serialize_contact(c)
        for c in investor.contacts.all()
    ]
    meetings = [
        {
            'id': m.pk,
            'date': _iso(m.date),
            'participants': m.participants or [],
            'investor_participants': m.investor_participants or [],
            'notes': m.notes or '',
        }
        for m in investor.meeting_logs.all()[:50]
    ]
    calls = [
        {
            'id': c.pk,
            'date': _iso(c.date),
            'with': c.with_display,
            'notes': c.notes or '',
        }
        for c in investor.call_logs.all()[:50]
    ]
    emails = [
        {
            'id': e.pk,
            'date': _iso(e.date),
            'with': e.with_display,
            'direction': e.direction,
            'subject': e.subject or '',
            'notes': e.notes or '',
        }
        for e in investor.email_logs.all()[:50]
    ]
    commitments = [
        {
            'id': o.pk,
            'fund': o.fund,
            'amount': _dec(o.amount) if hasattr(o, 'amount') else None,
            'date': _iso(o.date) if o.date else None,
            'notes': o.notes or '',
        }
        for o in investor.commitments.all()
    ]
    co_investments = [
        {
            'id': c.pk,
            'name': c.name,
            'size': _dec(c.size) if c.size is not None else None,
            'decision': c.decision,
            'date': _iso(c.date) if c.date else None,
        }
        for c in investor.co_investments.all()
    ]
    findings = [
        serialize_finding(n)
        for n in investor.agent_notes.select_related('author', 'investor')[:50]
    ]
    data = serialize_investor_summary(investor)
    data.update(
        {
            'about': investor.about or '',
            'vdr_access': investor.vdr_access,
            'vdr_access_date': _iso(investor.vdr_access_date),
            'meeting': investor.meeting,
            'prefequity_owner': investor.prefequity_owner or '',
            'responsibility': (
                investor.responsibility.name if investor.responsibility_id else None
            ),
            'intermediary': (
                investor.intermediary.name if investor.intermediary_id else None
            ),
            'contacts': contacts,
            'activity': {
                'meetings': meetings,
                'calls': calls,
                'emails': emails,
            },
            'commitments': commitments,
            'co_investments': co_investments,
            'findings': findings,
        }
    )
    return data
