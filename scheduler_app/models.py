from django.db import models
from django.forms import ValidationError


# Create your models here.
class Faculty(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
    class Meta: 
        verbose_name_plural = "Faculties"

class Classroom(models.Model):
    name = models.CharField(max_length=50, help_text="eg., Room 101, Lab A")
    capacity = models.PositiveIntegerField(default=30)

    def __str__(self):
        return self.name

class Section(models.Model):
    name=models.CharField(max_length=12, help_text="eg., Section A, Section B")

    def __str__(self):
        return self.name

class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code}: {self.name}"

# --- New Model structure for team teaching ---
class CourseOffering(models.Model):
    """
    Defines a single course offering for a section, including total hour requirements.
    Faculty members are linked via the FacultyAssignment model below.
    """
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    
    required_theory_hours = models.PositiveIntegerField(default=3)
    required_tutorial_hours = models.PositiveIntegerField(default=1)

    class Meta:
        # A subject can only be offered once to a section.
        unique_together = ('subject', 'section')

    def __str__(self):
        return f"{self.subject.name} for {self.section.name}"
    
class FacultyAssignment(models.Model):
    """Links faculty members to a specific course offering defiining what they teach
    theory or tutorial"""
    class ClassTypeResponsibility(models.TextChoices):
        ALL = 'ALL', 'All Classes (Theory and Tutorial)'
        THEORY_ONLY = 'THEORY', 'Theory Only'
        TUTORIAL_ONLY = 'TUTORIAL', 'Tutorial Only'

    course_offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name="faculty_assignments")
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="course_assignments")
    responsibility = models.CharField(
        max_length=20,
        choices=ClassTypeResponsibility.choices,
        default=ClassTypeResponsibility.ALL,
        help_text="Defines which part of the course this faculty member teaches."
    )
    class Meta:
        # Prevents assigning the same faculty member twice to the exact same course offering.
        unique_together = ('course_offering', 'faculty')

    def __str__(self):
        return f"{self.faculty.name} teaches {self.responsibility} for {self.course_offering}"

    def clean(self):
        """Validation for the 'at most two subjects per faculty' rule."""
        super().clean()
        if self.faculty:
            # Get all course offerings this faculty is assigned to, excluding the current assignment instance.
            assigned_offerings = FacultyAssignment.objects.filter(faculty=self.faculty).exclude(pk=self.pk)
            # Find distinct subject IDs from those offerings.
            distinct_subject_ids = set(assigned_offerings.values_list('course_offering__subject_id', flat=True))
            
            # Check if the new subject adds to the count.
            is_new_subject = self.course_offering.subject_id not in distinct_subject_ids
            current_subject_count = len(distinct_subject_ids)
            
            if is_new_subject and current_subject_count >= 2:
                raise ValidationError(
                    f"Validation Failed: Faculty '{self.faculty}' is already assigned to {current_subject_count} distinct subjects. "
                    f"Cannot assign to a new subject '{self.course_offering.subject}'. A faculty can teach at most 2 subjects."
                )

# scheduler/models.py (continuation)

# --- Timetable Result Model ---

class ScheduledClass(models.Model):
    """
    Represents the final, scheduled timetable slot.
    It stores direct links to the core entities (denormalized) for easy querying and historical integrity.
    """
    class ClassType(models.TextChoices):
        THEORY = 'THEORY', 'Theory'
        TUTORIAL = 'TUTORIAL', 'Tutorial'

    # Scheduling details
    DAYS_OF_WEEK = [(i, f"Day {i}") for i in range(1, 7)] # Assuming 6-day week (Mon-Sat)
    PERIODS = [(i, f"Period {i}") for i in range(1, 9)] # Assuming 8 periods per day

    day = models.IntegerField(choices=DAYS_OF_WEEK)
    period = models.PositiveIntegerField()
    # We use PROTECT to prevent deleting a faculty member if they are part of a generated schedule.
    faculty = models.ForeignKey(Faculty, on_delete=models.PROTECT, related_name="scheduled_classes")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="scheduled_classes")
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="scheduled_classes")
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="scheduled_classes")
    
    class_type = models.CharField(max_length=10, choices=ClassType.choices)

    class Meta:
        # Constraints to prevent resource conflicts during runtime.
        unique_together = [
            ('day', 'period', 'classroom'),    # A classroom can only have one class at a time.
            ('day', 'period', 'section'),      # A section can only attend one class at a time.
            ('day', 'period', 'faculty'),      # A faculty member can only teach one class at a time.
        ]
        ordering = ['day', 'period', 'section']

    def __str__(self):
        return f"Day {self.day}, Period {self.period}: {self.section} - {self.subject.code} ({self.faculty.name})"
