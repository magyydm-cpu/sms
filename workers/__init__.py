"""Background workers (reserved for phase 3: message sending and reminders).

Phase 1/2 intentionally runs no background service: messaging, scheduling and
notification delivery need Android-specific runtime permissions and jobs that
are out of scope until phase 3.
"""
