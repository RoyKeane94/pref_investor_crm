"""
URL configuration for investor_crm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from crm import views as crm_views

urlpatterns = [
    # Browsers often request /favicon.ico before parsing the page
    path(
        'favicon.ico',
        RedirectView.as_view(
            url=f"{settings.STATIC_URL.rstrip('/')}/favicon.png",
            permanent=False,
        ),
    ),
    path('admin/', admin.site.urls),
    path('accounts/register/', crm_views.register, name='register'),
    path('accounts/login/', crm_views.login_view, name='login'),
    path('accounts/logout/', crm_views.logout_view, name='logout'),
    path('', include('crm.urls', namespace='crm')),
]
