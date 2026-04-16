/**
 * ops/load-test.js — k6 baseline for Flow Procurement.
 *
 * Run locally against staging or prod (be careful on prod):
 *   k6 run -e BASE_URL=https://flow-procurement.up.railway.app ops/load-test.js
 *
 * Or with custom ramp:
 *   k6 run --vus 20 --duration 2m ops/load-test.js
 *
 * Thresholds are the SLOs we care about. CI will flip this into a
 * non-functional gate once we wire the k6 cloud or a local runner.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

const errorRate = new Rate('api_errors');
const optimizeDuration = new Trend('optimize_ms');
const scorecardDuration = new Trend('scorecard_ms');

export const options = {
  stages: [
    { duration: '30s', target: 5 },   // warm up
    { duration: '1m', target: 10 },   // sustained
    { duration: '30s', target: 0 },   // drain
  ],
  thresholds: {
    // 99% of requests under 1.5s is our soft SLO
    http_req_duration: ['p(95)<1500', 'p(99)<3000'],
    // Error rate under 1% — prod-ready bar
    api_errors: ['rate<0.01'],
    // Individual heavy endpoints get their own budget
    optimize_ms: ['p(95)<2500'],
    scorecard_ms: ['p(95)<1500'],
  },
};

export default function () {
  // 1. Cheap happy path — dashboard loads
  const health = http.get(`${BASE_URL}/health`);
  check(health, { 'health 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 2. Metrics endpoint — should be cheap even under load
  const metrics = http.get(`${BASE_URL}/metrics`);
  check(metrics, { 'metrics 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 3. BI status — proves adapters don't fan out badly
  const bi = http.get(`${BASE_URL}/api/v1/bi/status`);
  check(bi, { 'bi 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 4. Spend analytics — small fan-out over orders
  const spend = http.get(`${BASE_URL}/api/v1/buying/spend-analytics?period_days=90`);
  check(spend, { 'spend 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 5. Taxonomy — walks full subdomain tree
  const tax = http.get(`${BASE_URL}/api/v1/domains/extended`);
  check(tax, { 'taxonomy 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 6. Scorecard — biggest join surface we ship
  const scorecard = http.get(`${BASE_URL}/api/v1/buying/suppliers/scorecard?limit=20`);
  check(scorecard, { 'scorecard 200': (r) => r.status === 200 }) || errorRate.add(1);
  scorecardDuration.add(scorecard.timings.duration);

  // 7. Recommendations — rules engine fan-out
  const recs = http.get(`${BASE_URL}/api/v1/copilot/recommendations?step=0`);
  check(recs, { 'recs 200': (r) => r.status === 200 }) || errorRate.add(1);

  // 8. Heavy path: subdomain optimiser (one per iteration is enough)
  if (Math.random() < 0.3) {
    const optim = http.get(`${BASE_URL}/api/v1/dashboard/subdomain-aggregate/demo?domain=parts`);
    check(optim, { 'optim 200': (r) => r.status === 200 }) || errorRate.add(1);
    optimizeDuration.add(optim.timings.duration);
  }

  sleep(1);
}
