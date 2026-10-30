from functools import wraps
from typing import Callable

from django.contrib.auth.models import Group, User
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden

READ_ONLY_GROUP_NAME = 'Read Only'


def get_read_only_group() -> Group:
    group, _ = Group.objects.get_or_create(name=READ_ONLY_GROUP_NAME)
    return group


def assign_read_only(user: User) -> None:
    user.groups.add(get_read_only_group())


def user_can_write(user: User) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    return not user.groups.filter(name=READ_ONLY_GROUP_NAME).exists()


def write_required(view_func: Callable) -> Callable:
    """Block create/update/delete views for read-only users."""

    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not user_can_write(request.user):
            return HttpResponseForbidden('You have read-only access.')
        return view_func(request, *args, **kwargs)

    return _wrapped


def can_write_context(request: HttpRequest) -> dict[str, bool]:
    return {'can_write': user_can_write(request.user)}
