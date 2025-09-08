# scheduler/management/commands/generate_timetable.py

from django.core.management.base import BaseCommand
from scheduler_app.scheduler_service import TimetableORToolsSolver 

class Command(BaseCommand):
    help = 'Generates the weekly class timetable using Google OR-Tools.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting timetable generation process..."))
        
        # Initialize and run the solver
        scheduler = TimetableORToolsSolver()
        success, message = scheduler.solve()
        
        if success:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stdout.write(self.style.ERROR(message)) 
