import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    create_appointments: {
      executor: "ramping-vus",
      stages: [
        { duration: "30s", target: 50 },
        { duration: "1m", target: 50 },
        { duration: "30s", target: 0 }
      ],
      exec: "createAppointment"
    },
    get_appointments: {
      executor: "constant-vus",
      vus: 25,
      duration: "2m",
      exec: "getAppointments"
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"]
  }
};

const baseUrl = __ENV.BASE_URL || "http://localhost:7071/api";
const authHeaders = { "Content-Type": "application/json", Authorization: `Bearer ${__ENV.TOKEN || ""}` };

export function createAppointment() {
  const payload = JSON.stringify({
    insuredId: `${10000 + (__VU % 1000)}`,
    scheduleId: 10
  });

  const response = http.post(`${baseUrl}/appointments`, payload, { headers: authHeaders });

  check(response, {
    "create accepted": (r) => r.status === 202
  });

  sleep(1);
}

export function getAppointments() {
  const insuredId = `${10000 + (__VU % 1000)}`;
  const response = http.get(`${baseUrl}/appointments/${insuredId}`, { headers: authHeaders });

  check(response, {
    "query succeeded": (r) => r.status === 200
  });

  sleep(1);
}
