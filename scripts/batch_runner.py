"""Batch runner — Integration Standard IS-10.

Runs a folder or file of test inputs against the API and writes all results
to one output folder.

Usage:
  python scripts/batch_runner.py --input tests/batch_inputs/ --output results/ --base-url http://localhost:8000 --token YOUR_TOKEN
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx


async def run_single(client: httpx.AsyncClient, input_file: Path, output_dir: Path) -> None:
    payload = json.loads(input_file.read_text(encoding="utf-8"))
    idempotency_key = f"batch-{input_file.stem}-{int(time.time())}"
    start = time.perf_counter()
    try:
        resp = await client.post(
            "/api/v1/publish",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        elapsed = time.perf_counter() - start
        result = {
            "input_file": str(input_file),
            "status_code": resp.status_code,
            "response": resp.json(),
            "elapsed_ms": round(elapsed * 1000, 1),
        }

        # Poll for job completion if 202
        if resp.status_code == 202:
            job_id = resp.json().get("job_id")
            for _ in range(20):
                await asyncio.sleep(1)
                job_resp = await client.get(f"/api/v1/jobs/{job_id}")
                job_data = job_resp.json()
                result["job"] = job_data
                if job_data.get("status") in ("succeeded", "failed"):
                    break

    except Exception as exc:
        elapsed = time.perf_counter() - start
        result = {"input_file": str(input_file), "error": str(exc), "elapsed_ms": round(elapsed * 1000, 1)}

    out_file = output_dir / f"{input_file.stem}_result.json"
    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    status = result.get("status_code") or "ERR"
    print(f"  [{status}] {input_file.name} → {out_file.name} ({result.get('elapsed_ms', 0)}ms)")


async def main(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        files = [input_path]
    else:
        files = sorted(input_path.glob("*.json"))

    print(f"Batch runner: {len(files)} input(s) → {output_dir}")
    async with httpx.AsyncClient(
        base_url=args.base_url,
        headers={"Authorization": f"Bearer {args.token}"},
        timeout=60,
    ) as client:
        tasks = [run_single(client, f, output_dir) for f in files]
        await asyncio.gather(*tasks)

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IncuBrix Distribution batch runner")
    parser.add_argument("--input", required=True, help="Input file or directory of JSON inputs")
    parser.add_argument("--output", default="batch_results", help="Output directory")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--token", required=True, help="API bearer token")
    asyncio.run(main(parser.parse_args()))
