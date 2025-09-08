import collections
from ortools.sat.python import cp_model

from .models import (
    CourseOffering, FacultyAssignment, Classroom, ScheduledClass, 
    Section, Subject, Faculty
)

# --- Define Time Grid Constants ---
# Assuming a 6-day week (Monday-Saturday) and 8 periods per day.
# Adjust these values if your school's schedule differs.
DAYS = range(1, 7)  # 1 = Monday, 2 = Tuesday, ..., 6 = Saturday
PERIODS = range(1, 9) # 1 through 8

class TimetableORToolsSolver:
    """
    Solves the timetabling problem using Google OR-Tools CP-SAT solver.
    Reads course requirements and faculty assignments from Django models,
    applies constraints, and saves the generated schedule.
    """
    def __init__(self):
        # 1. Load data from database into memory
        self.all_sections = list(Section.objects.all())
        self.all_classrooms = list(Classroom.objects.all())
        self.all_faculties = list(Faculty.objects.all())
        
        # 2. Initialize CP-SAT model and solver components
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.variables = {}  # Dictionary to hold solver variables: {(req_id, day, period, room_id): var}

    def solve(self):
        """Main method to run the solver process."""
        # 1. Prepare flat list of class requirements from complex models
        self.class_requirements = self._prepare_class_requirements()
        if not self.class_requirements:
            return False, "No class requirements generated. Check CourseOfferings and FacultyAssignments in admin."

        # Data validation for resource capacity
        total_required_slots = len(self.class_requirements)
        available_slots = len(self.all_classrooms) * len(DAYS) * len(PERIODS)
        if total_required_slots > available_slots:
            return False, f"Scheduling impossible: {total_required_slots} classes required, but only {available_slots} classroom slots available."

        print(f"Starting solver for {total_required_slots} class sessions...")

        # 2. Create solver variables
        self._create_variables()
        
        # 3. Apply all scheduling constraints
        self._apply_constraints()
        
        # 4. Run the solver
        status = self.solver.Solve(self.model)
        
        # 5. Process results
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print("Successfully found a valid schedule.")
            self._save_results()
            return True, "Schedule generated successfully."
        else:
            status_name = self.solver.StatusName(status)
            return False, f"Could not generate schedule (Solver status: {status_name}). Constraints may be too tight."

    # --- Step 1: Data Preparation ---
    def _prepare_class_requirements(self):
        """
        Processes CourseOffering and FacultyAssignment data to create a flat list
        of individual class sessions to be scheduled. Each session is assigned to a specific faculty member.
        """
        requirements = []
        req_id_counter = 0

        for offering in CourseOffering.objects.prefetch_related('faculty_assignments__faculty').all():
            assignments = list(offering.faculty_assignments.all())
            
            # --- Logic for Theory Classes ---
            theory_faculty = None
            for assign in assignments:
                if assign.responsibility in [FacultyAssignment.ClassTypeResponsibility.ALL, FacultyAssignment.ClassTypeResponsibility.THEORY_ONLY]:
                    theory_faculty = assign.faculty
                    break  # Use the first faculty found who is responsible for theory

            if theory_faculty:
                for _ in range(offering.required_theory_hours):
                    requirements.append({
                        "id": req_id_counter,
                        "subject": offering.subject,
                        "section": offering.section,
                        "faculty": theory_faculty,
                        "class_type": ScheduledClass.ClassType.THEORY,
                    })
                    req_id_counter += 1

            # --- Logic for Tutorial Classes ---
            tutorial_faculty = None
            for assign in assignments:
                if assign.responsibility in [FacultyAssignment.ClassTypeResponsibility.ALL, FacultyAssignment.ClassTypeResponsibility.TUTORIAL_ONLY]:
                    tutorial_faculty = assign.faculty
                    break  # Use the first faculty found who is responsible for tutorials
            
            if tutorial_faculty:
                for _ in range(offering.required_tutorial_hours):
                    requirements.append({
                        "id": req_id_counter,
                        "subject": offering.subject,
                        "section": offering.section,
                        "faculty": tutorial_faculty,
                        "class_type": ScheduledClass.ClassType.TUTORIAL,
                    })
                    req_id_counter += 1

        return requirements

    # --- Step 2: Solver Variable Creation ---
    def _create_variables(self):
        """Creates a boolean variable for each possible class session placement."""
        for req in self.class_requirements:
            req_id = req["id"]
            for day in DAYS:
                for period in PERIODS:
                    for room in self.all_classrooms:
                        self.variables[(req_id, day, period, room.id)] = self.model.NewBoolVar(
                            f"session_{req_id}_day{day}_p{period}_room{room.id}"
                        )

    # --- Step 3: Constraint Application ---
    def _apply_constraints(self):
        """Applies all scheduling rules to the CP-SAT model."""
        
        # --- Constraint 1: Schedule each class requirement exactly once ---
        for req in self.class_requirements:
            self.model.AddExactlyOne(
                self.variables[(req["id"], day, period, room.id)]
                for day in DAYS for period in PERIODS for room in self.all_classrooms
            )

        # --- Resource Constraints (at most one activity per resource per time slot) ---
        for day in DAYS:
            for period in PERIODS:
                # Constraint 2: A section can attend only one class at a time.
                for section in self.all_sections:
                    req_ids_for_section = [r["id"] for r in self.class_requirements if r["section"] == section]
                    self.model.AddAtMostOne(
                        self.variables[(req_id, day, period, room.id)]
                        for req_id in req_ids_for_section for room in self.all_classrooms
                    )

                # Constraint 3: A classroom can host only one class at a time.
                for room in self.all_classrooms:
                    req_ids_for_room = [r["id"] for r in self.class_requirements]
                    self.model.AddAtMostOne(
                        self.variables[(req_id, day, period, room.id)]
                        for req_id in req_ids_for_room
                    )

                # Constraint 4: A faculty member can teach only one class at a time.
                for faculty in self.all_faculties:
                    req_ids_for_faculty = [r["id"] for r in self.class_requirements if r["faculty"] == faculty]
                    if req_ids_for_faculty: # Only add constraint if faculty has assigned classes
                        self.model.AddAtMostOne(
                            self.variables[(req_id, day, period, room.id)]
                            for req_id in req_ids_for_faculty for room in self.all_classrooms
                        )

        # --- Constraint 5: No consecutive classes for the same subject and section ---
        # "A section cannot have Subject X in Period 1 and Subject X again in Period 2."
        for section in self.all_sections:
            for subject in Subject.objects.filter(courseoffering__section=section).distinct():
                req_ids_for_subject_section = [
                    r["id"] for r in self.class_requirements 
                    if r["section"] == section and r["subject"] == subject
                ]
                
                for day in DAYS:
                    for p1 in PERIODS:
                        if p1 + 1 in PERIODS:
                            p2 = p1 + 1
                            
                            # Create temporary boolean variables representing: "Is subject active in period p1/p2?"
                            is_active_p1 = self.model.NewBoolVar(f"active_{section.id}_{subject.id}_d{day}_p{p1}")
                            is_active_p2 = self.model.NewBoolVar(f"active_{section.id}_{subject.id}_d{day}_p{p2}")

                            # Link temporary variables to actual schedule variables.
                            # is_active_p1 = True if any class for this subject/section is scheduled in period p1.
                            self.model.Add(is_active_p1 == sum(
                                self.variables[(req_id, day, p1, room.id)]
                                for req_id in req_ids_for_subject_section for room in self.all_classrooms
                            ))
                            self.model.Add(is_active_p2 == sum(
                                self.variables[(req_id, day, p2, room.id)]
                                for req_id in req_ids_for_subject_section for room in self.all_classrooms
                            ))

                            # Constraint: At most one of [is_active_p1, is_active_p2] can be true.
                            self.model.AddAtMostOne([is_active_p1, is_active_p2])

    # --- Step 4: Save Results ---
    def _save_results(self):
        """Saves the solved timetable from the solver memory into the ScheduledClass database model."""
        ScheduledClass.objects.all().delete() # Clear old schedule first
        new_classes = []
        req_lookup = {r["id"]: r for r in self.class_requirements} # Easy lookup by ID

        for (req_id, day, period, room_id), var in self.variables.items():
            if self.solver.Value(var) == 1:
                req_data = req_lookup[req_id]
                new_classes.append(ScheduledClass(
                    day=day,
                    period=period,
                    classroom_id=room_id,
                    faculty=req_data["faculty"],
                    subject=req_data["subject"],
                    section=req_data["section"],
                    class_type=req_data["class_type"]
                ))
        
        ScheduledClass.objects.bulk_create(new_classes)
        print(f"Successfully saved {len(new_classes)} scheduled classes to database.")