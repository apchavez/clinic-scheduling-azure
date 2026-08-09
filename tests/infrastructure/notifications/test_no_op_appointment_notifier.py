from clinic.domain.entities.appointment import Appointment
from clinic.infrastructure.notifications.no_op_appointment_notifier import NoOpAppointmentNotifier


def test_no_op_methods_do_nothing():
    notifier = NoOpAppointmentNotifier()
    a = Appointment.create("a1", "12345", 1)
    notifier.notify_completed(a)
