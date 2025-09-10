from django.shortcuts import render
from .models import ScheduledClass, Section

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

def generate_period_times(start="10:00", duration=50, periods=8, breaks=None):
    """
    Returns list of slots. Each slot is:
      - period: {"type":"period", "label":"Period X", "start": "HH:MM", "end":"HH:MM", "index": X}
      - break:  {"type":"break",  "label":"Lunch Break" or custom, "start": "HH:MM", "end":"HH:MM", "index": None}
    `breaks` is a dict mapping period_number -> break_minutes (e.g. {4:60} adds 60-min break after period 4).
    """
    from datetime import datetime, timedelta

    if breaks is None:
        breaks = {}

    start_time = datetime.strptime(start, "%H:%M")
    result = []

    for i in range(1, periods + 1):
        end_time = start_time + timedelta(minutes=duration)
        result.append({
            "type": "period",
            "label": f"Period {i}",
            "start": start_time.strftime("%H:%M"),
            "end": end_time.strftime("%H:%M"),
            "index": i
        })
        start_time = end_time

        # If a break is specified after period i, insert it immediately
        if i in breaks:
            break_end = start_time + timedelta(minutes=breaks[i])
            # choose a label; you can customize the label mapping if you want more specific break names
            break_label = "Lunch Break" if breaks[i] >= 30 and i == 4 else f"Break after {i}"
            result.append({
                "type": "break",
                "label": break_label,
                "start": start_time.strftime("%H:%M"),
                "end": break_end.strftime("%H:%M"),
                "index": None
            })
            start_time = break_end

    return result


def view_timetable(request):
    sections = Section.objects.all()
    selected_section_id = request.GET.get('section_id')
    table_rows = []

    # --- Customize start/duration/periods/breaks as needed ---
    PERIOD_TIMES = generate_period_times(start="10:00", duration=50, periods=8, breaks={4: 60})
    # ---------------------------------------------------------

    # Build a map: real period number -> its period slot in PERIOD_TIMES
    period_slot_map = {slot["index"]: slot for slot in PERIOD_TIMES if slot["type"] == "period"}

    # number of actual periods (e.g., 8)
    actual_period_count = max(period_slot_map.keys()) if period_slot_map else 0

    if selected_section_id:
        # fetch scheduled classes for the selected section
        scheduled_classes = ScheduledClass.objects.filter(
            section_id=selected_section_id
        ).select_related('subject', 'faculty', 'classroom')

        # temp grid keyed by day (1..6) and period (1..actual_period_count)
        temp_grid = {day: {p: None for p in range(1, actual_period_count + 1)} for day in range(1, 7)}

        for s_class in scheduled_classes:
            # ensure s_class.period is within expected range
            period_num = s_class.period
            if 1 <= period_num <= actual_period_count:
                slot = period_slot_map.get(period_num)
                temp_grid[s_class.day][period_num] = {
                    "subject": str(s_class.subject),
                    "faculty": str(s_class.faculty),
                    "classroom": str(s_class.classroom),
                    "start_time": slot["start"] if slot else None,
                    "end_time": slot["end"] if slot else None,
                }

        # Build table_rows: for each day, iterate over PERIOD_TIMES (so breaks are included in order)
        for day in range(1, 7):
            row = {"day_name": DAYS[day - 1], "cells": []}
            for slot in PERIOD_TIMES:
                if slot["type"] == "period":
                    # append the scheduled class (or None) for this period index
                    row["cells"].append(temp_grid[day][slot["index"]])
                else:  # break slot
                    row["cells"].append({
                        "break": slot["label"],
                        "start_time": slot["start"],
                        "end_time": slot["end"]
                    })
            table_rows.append(row)

    context = {
        "sections": sections,
        "selected_section_id": int(selected_section_id) if selected_section_id else None,
        "table_rows": table_rows,
        "period_headers": [
            f"{slot['label']} ({slot['start']} - {slot['end']})"
            for slot in PERIOD_TIMES
        ],
    }
    return render(request, "scheduler/timetable_display.html", context)
