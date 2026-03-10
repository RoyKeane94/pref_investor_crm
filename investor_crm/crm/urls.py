from django.urls import path

from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.investor_list, name='investor_list'),
    path('investors/<int:pk>/', views.investor_detail, name='investor_detail'),
    path('investors/create/', views.investor_create, name='investor_create'),
    path('investors/<int:pk>/edit/', views.investor_edit, name='investor_edit'),
    path('investors/<int:pk>/delete/', views.investor_delete, name='investor_delete'),
    path(
        'investors/<int:pk>/contacts/create/',
        views.contact_create,
        name='contact_create',
    ),
    path(
        'investors/<int:pk>/contacts/<int:contact_pk>/delete/',
        views.contact_delete,
        name='contact_delete',
    ),
    path(
        'investors/<int:pk>/calls/create/',
        views.calllog_create,
        name='calllog_create',
    ),
    path(
        'investors/<int:pk>/calls/<int:call_pk>/delete/',
        views.calllog_delete,
        name='calllog_delete',
    ),
    path(
        'investors/<int:pk>/emails/create/',
        views.emaillog_create,
        name='emaillog_create',
    ),
    path(
        'investors/<int:pk>/emails/<int:email_pk>/delete/',
        views.emaillog_delete,
        name='emaillog_delete',
    ),
    path(
        'investors/<int:pk>/coinvestments/create/',
        views.coinvestment_create,
        name='coinvestment_create',
    ),
    path(
        'investors/<int:pk>/coinvestments/<int:coinvest_pk>/delete/',
        views.coinvestment_delete,
        name='coinvestment_delete',
    ),
    path(
        'investors/<int:pk>/commitments/create/',
        views.commitment_create,
        name='commitment_create',
    ),
    path(
        'investors/<int:pk>/commitments/<int:commit_pk>/delete/',
        views.commitment_delete,
        name='commitment_delete',
    ),
    path(
        'investors/<int:pk>/infolinks/create/',
        views.infolink_create,
        name='infolink_create',
    ),
    path(
        'investors/<int:pk>/infolinks/<int:link_pk>/delete/',
        views.infolink_delete,
        name='infolink_delete',
    ),
    path(
        'investors/<int:pk>/reminders/create/',
        views.reminder_create,
        name='reminder_create',
    ),
    path(
        'investors/<int:pk>/reminders/<int:reminder_pk>/done/',
        views.reminder_done,
        name='reminder_done',
    ),
    path(
        'investors/<int:pk>/reminders/<int:reminder_pk>/delete/',
        views.reminder_delete,
        name='reminder_delete',
    ),
    path('reminders/all/', views.reminders_banner, name='reminders_banner'),
]
