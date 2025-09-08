from django.contrib import admin
from .models import Faculty, Section, Subject, Classroom, CourseOffering, FacultyAssignment, ScheduledClass
# Register your models here.

admin.site.register(Faculty)
admin.site.register(Section)
admin.site.register(Subject)
admin.site.register(Classroom)
admin.site.register(CourseOffering)
admin.site.register(FacultyAssignment)
admin.site.register(ScheduledClass)

