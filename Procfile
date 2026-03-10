web: cd investor_crm && python manage.py collectstatic --noinput && gunicorn investor_crm.wsgi:application --bind 0.0.0.0:${PORT:-8000}
