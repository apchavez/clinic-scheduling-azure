"""Appointment lifecycle: pending -> completed. Mirrors the status tracking from the AWS project."""

from enum import Enum


class AppointmentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
