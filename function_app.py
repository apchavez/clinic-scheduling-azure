"""Azure Functions Python v2 entry points. Adapts HTTP/Service Bus triggers to domain use cases
resolved by app_context. The domain, use cases and adapters are unchanged across ports - only
this entry layer differs by language/runtime.

authLevel is ANONYMOUS on every HTTP trigger (no Azure Functions key required) - AuthGuard
enforces the actual auth check explicitly inside each handler body, exactly like the Java port.
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

from clinic.domain.exceptions import ForbiddenError, IllegalStateError
from clinic.infrastructure.auth import auth_guard
from clinic.infrastructure.auth.jwt_validator import AuthenticationError
from clinic.infrastructure.config import app_context, correlation_context
from clinic.shared import api_response
from clinic.shared.health_status import UP, HealthStatus

log = logging.getLogger("clinic")

app = func.FunctionApp()


def _correlation_id(req: func.HttpRequest, context: func.Context) -> str:
    return req.headers.get("X-Correlation-Id") or context.invocation_id


def _mask_insured_id(insured_id: str | None) -> str:
    """Masks all but the last 4 characters so logs stay useful for correlation without
    writing a patient-identifying value in clear text."""
    if not insured_id:
        return ""
    return f"***{insured_id[-4:]}" if len(insured_id) > 4 else "***"


@app.route(route="appointments", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def create_appointment(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    correlation_id = _correlation_id(req, context)
    correlation_context.set_correlation_id(correlation_id)
    try:
        log.info(
            "createAppointment.received correlationId=%s invocationId=%s",
            correlation_id,
            context.invocation_id,
        )
        user = auth_guard.authenticate(req)
        body = json.loads(req.get_body() or b"{}")

        insured_id = body.get("insuredId")
        schedule_id = body.get("scheduleId")
        contact_email = body.get("contactEmail")

        if not insured_id or not isinstance(schedule_id, int) or schedule_id < 1:
            return api_response.error(
                400,
                "Invalid request: insuredId and scheduleId>=1 are required",
            )
        if user.role == "insured" and insured_id != user.sub:
            return api_response.error(403, "insured can only book appointments for themselves")

        appointment = app_context.create_appointment().execute(
            insured_id, schedule_id, contact_email
        )
        log.info(
            "appointment.accepted appointmentId=%s insuredId=%s correlationId=%s",
            appointment.appointment_id,
            _mask_insured_id(appointment.insured_id),
            correlation_id,
        )
        return api_response.accepted(
            {
                "appointmentId": appointment.appointment_id,
                "message": "Appointment received",
                "status": "pending",
            }
        )
    except AuthenticationError as e:
        log.warning("createAppointment.unauthorized reason=%s correlationId=%s", e, correlation_id)
        return api_response.error(401, f"Unauthorized: {e}")
    except Exception as e:  # noqa: BLE001
        log.error("Error creating appointment: %s correlationId=%s", e, correlation_id, exc_info=e)
        return api_response.error(500, "Internal error processing appointment")
    finally:
        correlation_context.clear()


@app.route(route="appointments/{insuredId}", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_appointments(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    insured_id = req.route_params.get("insuredId")
    correlation_id = _correlation_id(req, context)
    correlation_context.set_correlation_id(correlation_id)
    try:
        log.info(
            "getAppointments.received insuredId=%s correlationId=%s", insured_id, correlation_id
        )
        user = auth_guard.authenticate(req)
        if not insured_id:
            return api_response.error(400, "insuredId path parameter is required")
        if user.role == "insured" and insured_id != user.sub:
            return api_response.error(403, "insured can only view their own appointments")

        page_size = _parse_page_size(req.params.get("pageSize"))
        cursor = req.params.get("cursor")

        page = app_context.get_appointments().by_insured_paged(insured_id, page_size, cursor)

        log.info(
            "appointments.queried insuredId=%s count=%d hasNextPage=%s correlationId=%s",
            insured_id,
            len(page.items),
            page.next_cursor is not None,
            correlation_id,
        )
        return api_response.ok(page)
    except AuthenticationError as e:
        log.warning("getAppointments.unauthorized reason=%s correlationId=%s", e, correlation_id)
        return api_response.error(401, f"Unauthorized: {e}")
    except Exception as e:  # noqa: BLE001
        log.error("Error querying appointments: %s correlationId=%s", e, correlation_id, exc_info=e)
        return api_response.error(500, "Internal error querying appointments")
    finally:
        correlation_context.clear()


def _parse_page_size(raw: str | None) -> int:
    from clinic.application.usecases.get_appointments import DEFAULT_PAGE_SIZE

    if not raw:
        return DEFAULT_PAGE_SIZE
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PAGE_SIZE


@app.route(
    route="appointments/{appointmentId}/history",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def get_appointment_history(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    appointment_id = req.route_params.get("appointmentId")
    correlation_id = _correlation_id(req, context)
    correlation_context.set_correlation_id(correlation_id)
    try:
        log.info(
            "getAppointmentHistory.received appointmentId=%s correlationId=%s",
            appointment_id,
            correlation_id,
        )
        user = auth_guard.authenticate(req)
        if not appointment_id:
            return api_response.error(400, "appointmentId path parameter is required")

        events = app_context.get_appointment_history().execute(appointment_id, user)

        log.info(
            "appointment.history appointmentId=%s eventCount=%d correlationId=%s",
            appointment_id,
            len(events),
            correlation_id,
        )
        return api_response.ok(events)
    except AuthenticationError as e:
        log.warning(
            "getAppointmentHistory.unauthorized reason=%s correlationId=%s", e, correlation_id
        )
        return api_response.error(401, f"Unauthorized: {e}")
    except ForbiddenError as e:
        log.warning(
            "getAppointmentHistory.forbidden appointmentId=%s reason=%s correlationId=%s",
            appointment_id,
            e,
            correlation_id,
        )
        return api_response.error(403, str(e))
    except IllegalStateError as e:
        msg = str(e)
        if msg.startswith("Appointment not found"):
            return api_response.error(404, msg)
        return api_response.error(409, msg)
    except Exception as e:  # noqa: BLE001
        log.error(
            "Error fetching appointment history: %s correlationId=%s", e, correlation_id, exc_info=e
        )
        return api_response.error(500, "Internal error fetching appointment history")
    finally:
        correlation_context.clear()


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    try:
        status: HealthStatus = app_context.health_check()
        status_code = 200 if status.status == UP else 503
        return func.HttpResponse(
            json.dumps(
                {"status": status.status, "checks": status.checks, "timestamp": status.timestamp}
            ),
            status_code=status_code,
            mimetype="application/json",
        )
    except Exception as e:  # noqa: BLE001
        log.error("Health check error: %s", e, exc_info=e)
        return api_response.error(500, "Health check unavailable")


def _process_worker_message(message: str, context: func.Context) -> None:
    try:
        payload = json.loads(message)
        appointment_id = payload.get("appointmentId", "")
        correlation_id = payload.get("correlationId") or appointment_id
        log.info(
            "appointment.processing appointmentId=%s correlationId=%s invocationId=%s",
            appointment_id,
            correlation_id,
            context.invocation_id,
        )
        app_context.process_appointment().execute(appointment_id)
        log.info(
            "appointment.completed appointmentId=%s correlationId=%s invocationId=%s",
            appointment_id,
            correlation_id,
            context.invocation_id,
        )
    except Exception as e:  # noqa: BLE001
        log.error("Error processing message: %s", e)
        raise  # let Service Bus retry / dead-letter


@app.function_name(name="appointmentWorker")
@app.service_bus_topic_trigger(
    arg_name="message",
    topic_name="appointment-created",
    subscription_name="appointment-worker",
    connection="SERVICEBUS",
)
def appointment_worker(message: func.ServiceBusMessage, context: func.Context) -> None:
    _process_worker_message(message.get_body().decode("utf-8"), context)


def _process_confirmation_message(message: str, context: func.Context) -> None:
    try:
        payload = json.loads(message)
        # Event Grid's CloudEvent-schema delivery to Service Bus wraps the publisher's payload
        # under "data" (see EventGridConfirmationPublisher); appointmentId is the only field the
        # confirmation handler needs.
        data = payload.get("data", payload)
        appointment_id = data.get("appointmentId", "")
        log.info(
            "appointment.confirming appointmentId=%s invocationId=%s",
            appointment_id,
            context.invocation_id,
        )
        app_context.confirm_appointment().execute(appointment_id)
        log.info(
            "appointment.confirmed appointmentId=%s invocationId=%s",
            appointment_id,
            context.invocation_id,
        )
    except Exception as e:  # noqa: BLE001
        log.error("Error confirming appointment: %s", e)
        raise  # let Service Bus retry / dead-letter


@app.function_name(name="confirmAppointment")
@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="appointment-confirmations",
    connection="SERVICEBUS",
)
def confirm_appointment(message: func.ServiceBusMessage, context: func.Context) -> None:
    _process_confirmation_message(message.get_body().decode("utf-8"), context)
