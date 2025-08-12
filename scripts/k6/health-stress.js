import http from 'k6/http'
import { sleep, check } from 'k6'

export const options = {
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
}

const BASE = __ENV.TARGET_BASE_URL || 'https://silky-loss-production.up.railway.app'

export default function () {
  const res = http.get(`${BASE}/health`)
  check(res, { 'status 200': (r) => r.status === 200 })
  sleep(0.2)
}


