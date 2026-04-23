import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx


GATEWAY_URL = "http://127.0.0.1:1495"
FIRM_ORDER_URL = f"{GATEWAY_URL}/OKXDEX/rfq/firm-order"

REQUEST_DATA = {
    "chainIndex": "56",
    "takerAsset": "0x55d398326f99059ff775485246999027b3197955",
    "makerAsset": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "takerAmount": "1000000000000000000000",
    "takerAddress": "0x1234567890abcdef1234567890abcdef12345678",
    "rfqId": 8234567890123,
    "expiryDuration": 40,
    "beneficiaryAddress": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
    "confidenceT": 5,
    "confidenceRate": 2000,
    "confidenceCap": 30000
}
HEADERS = {
    "X-API-KEY": "newworld-api-key-Tm2s#88%sUs6",
    "Content-Type": "application/json"
}

QPS_LEVELS = [100, 200, 500, 1000]
TEST_DURATION = 100


async def send_request(client: httpx.AsyncClient) -> tuple:
    start = time.perf_counter()
    try:
        response = await client.post(FIRM_ORDER_URL, json=REQUEST_DATA, headers=HEADERS)
        latency = (time.perf_counter() - start) * 1000
        return latency, response.status_code
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return latency, 0


async def run_qps_test(qps: int) -> Dict[str, Any]:
    interval = 1.0 / qps
    latencies: List[float] = []
    errors = 0
    total_requests = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        start_time = time.time()
        next_request_time = start_time

        while time.time() - start_time < TEST_DURATION:
            now = time.time()
            if now >= next_request_time:
                total_requests += 1
                latency, status_code = await send_request(client)
                latencies.append(latency)
                if status_code != 200:
                    errors += 1
                next_request_time += interval

            await asyncio.sleep(0.0001)

        end_time = time.time()
        actual_duration = end_time - start_time
        actual_qps = total_requests / actual_duration

    latencies.sort()
    n = len(latencies)

    return {
        "target_qps": qps,
        "actual_qps": actual_qps,
        "total_requests": total_requests,
        "successful": n - errors,
        "errors": errors,
        "error_rate": errors / total_requests * 100 if total_requests > 0 else 0,
        "avg_latency": statistics.mean(latencies) if latencies else 0,
        "min_latency": min(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "p50": latencies[int(n * 0.5)] if n > 0 else 0,
        "p90": latencies[int(n * 0.9)] if n > 0 else 0,
        "p99": latencies[int(n * 0.99)] if n > 0 else 0,
    }


def print_result(result: Dict[str, Any]):
    print(f"\n{'='*60}")
    print(f"QPS: {result['target_qps']} (actual: {result['actual_qps']:.1f})")
    print(f"{'='*60}")
    print(f"Requests: {result['total_requests']} | Success: {result['successful']} | Errors: {result['errors']} | Error Rate: {result['error_rate']:.2f}%")
    print(f"Latency (ms):")
    print(f"  avg: {result['avg_latency']:.2f}")
    print(f"  min:  {result['min_latency']:.2f}")
    print(f"  max:  {result['max_latency']:.2f}")
    print(f"  p50:  {result['p50']:.2f}")
    print(f"  p90:  {result['p90']:.2f}")
    print(f"  p99:  {result['p99']:.2f}")


async def main():
    print(f"Starting stress test...")
    print(f"Gateway URL: {GATEWAY_URL}")
    print(f"Target URL: {FIRM_ORDER_URL}")
    print(f"Test duration per QPS: {TEST_DURATION}s")
    print(f"QPS levels: {QPS_LEVELS}")
    print(f"\nMake sure gateway and backend are running before starting!")

    results = []
    for qps in QPS_LEVELS:
        print(f"\n>>> Testing {qps} QPS...", end=" ", flush=True)
        result = await run_qps_test(qps)
        results.append(result)
        print(f"done")
        print_result(result)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"{'QPS':>8} | {'Actual QPS':>10} | {'Avg (ms)':>10} | {'P99 (ms)':>10} | {'Error %':>8}")
    print(f"{'-'*60}")
    for r in results:
        print(f"{r['target_qps']:>8} | {r['actual_qps']:>10.1f} | {r['avg_latency']:>10.2f} | {r['p99']:>10.2f} | {r['error_rate']:>8.2f}")


if __name__ == '__main__':
    asyncio.run(main())