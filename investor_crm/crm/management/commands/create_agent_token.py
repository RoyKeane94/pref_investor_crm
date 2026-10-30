from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from crm.models import AgentApiToken
from crm.permissions import is_agent_user

User = get_user_model()


class Command(BaseCommand):
    help = 'Create an MCP API bearer token for an agent (Read Only) user.'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            help='Agent user email (login email / username).',
        )
        parser.add_argument(
            '--name',
            default='MCP',
            help='Label for this token (default: MCP).',
        )

    def handle(self, *args, **options):
        email = options['email'].strip()
        name = options['name'].strip() or 'MCP'
        user = (
            User.objects.filter(email__iexact=email).first()
            or User.objects.filter(username__iexact=email).first()
        )
        if user is None:
            raise CommandError(f'No user found for {email!r}.')
        if not is_agent_user(user):
            self.stderr.write(
                self.style.WARNING(
                    f'{email} is not in the Read Only group; MCP will reject the token.'
                )
            )
        token, raw_key = AgentApiToken.create_token(user, name=name)
        self.stdout.write(self.style.SUCCESS(f'Created token id={token.pk} prefix={token.prefix}'))
        self.stdout.write('Copy this bearer token now; it will not be shown again:')
        self.stdout.write(raw_key)
