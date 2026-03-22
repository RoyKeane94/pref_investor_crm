from django.urls import path

from . import views

app_name = 'crm'

urlpatterns = [
    path('', views.investor_list, name='investor_list'),
    path('investors/import/', views.investor_import, name='investor_import'),
    path('investors/<int:pk>/', views.investor_detail, name='investor_detail'),
    path('investors/create/', views.investor_create, name='investor_create'),
    path('investors/<int:pk>/edit/', views.investor_edit, name='investor_edit'),
    path(
        'investors/<int:pk>/about/',
        views.investor_about_edit,
        name='investor_about_edit',
    ),
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
        'investors/<int:pk>/calls/<int:call_pk>/edit/',
        views.calllog_edit,
        name='calllog_edit',
    ),
    path(
        'investors/<int:pk>/meetings/create/',
        views.meetinglog_create,
        name='meetinglog_create',
    ),
    path(
        'investors/<int:pk>/meetings/<int:meeting_pk>/edit/',
        views.meetinglog_edit,
        name='meetinglog_edit',
    ),
    path(
        'investors/<int:pk>/meetings/<int:meeting_pk>/delete/',
        views.meetinglog_delete,
        name='meetinglog_delete',
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
        'investors/<int:pk>/emails/<int:email_pk>/edit/',
        views.emaillog_edit,
        name='emaillog_edit',
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
        'investors/<int:pk>/coinvestments/<int:coinvest_pk>/edit/',
        views.coinvestment_edit,
        name='coinvestment_edit',
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
        'investors/<int:pk>/commitments/<int:commit_pk>/edit/',
        views.commitment_edit,
        name='commitment_edit',
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
        'investors/<int:pk>/infolinks/<int:link_pk>/edit/',
        views.infolink_edit,
        name='infolink_edit',
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
