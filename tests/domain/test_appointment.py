import pytest

from clinic.domain.entities.appointment import Appointment
from clinic.domain.entities.appointment_status import AppointmentStatus
from clinic.domain.exceptions import IllegalStateError


def _pending():
    return Appointment.create("apt-1", "12345", 10)


def test_create_sets_pending_status_and_created_at():
    a = _pending()
    assert a.status == AppointmentStatus.PENDING
    assert a.created_at is not None
    assert a.appointment_id == "apt-1"
    assert a.insured_id == "12345"
    assert a.schedule_id == 10


def test_mark_completed_from_pending():
    a = _pending()
    a.mark_completed()
    assert a.status == AppointmentStatus.COMPLETED
    assert a.completed_at is not None


def test_mark_completed_rejects_non_pending():
    a = _pending()
    a.mark_completed()
    with pytest.raises(IllegalStateError):
        a.mark_completed()
