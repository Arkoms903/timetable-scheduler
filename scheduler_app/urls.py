from django.urls import path
from . import views

urlpatterns = [
    path('timetable/', views.view_timetable, name='view_timetable'),
]