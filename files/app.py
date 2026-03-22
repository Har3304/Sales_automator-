import os
import time
import traceback
import threading
from flask import Flask, render_template, request, jsonify
from scraper import scrape_lead
from analyzer import analyze_lead
from storage import save_result, load_all_results, clear_results
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
jobs = {}
jobs_lock = threading.Lock()


def _parse_leads(raw):
    return [line.strip() for line in raw.strip().splitlines() if line.strip()]


def _run_job(job_id, leads):
    with jobs_lock:
        jobs[job_id] = {"status": "running", "total": len(leads), "done": 0, "results": [], "errors": []}

    for lead in leads:
        with jobs_lock:
            jobs[job_id]["current"] = lead

        try:
            logger.info("Scraping: %s", lead)
            scraped = scrape_lead(lead)
            logger.info("Scrape done — success=%s len=%d", scraped.get("success"), len(scraped.get("content", "")))

            result = analyze_lead(lead, scraped)
            logger.info("Analysis done — b2b_qualified=%s", result.get("b2b_qualified"))

            save_result(result)
            with jobs_lock:
                jobs[job_id]["results"].append(result)

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Error on lead '%s':\n%s", lead, tb)

            error_result = {
                "lead": lead,
                "url": "",
                "source_type": "error",
                "scraped_success": False,
                "company_overview": "Error: " + str(exc),
                "core_product": "-",
                "target_customer": "-",
                "b2b_qualified": "Uncertain",
                "b2b_reasoning": str(exc),
                "sales_questions": [],
            }
            save_result(error_result)
            with jobs_lock:
                jobs[job_id]["results"].append(error_result)
                jobs[job_id]["errors"].append({"lead": lead, "error": str(exc), "traceback": tb})

        with jobs_lock:
            jobs[job_id]["done"] += 1

    with jobs_lock:
        jobs[job_id]["status"] = "done"
    logger.info("Job %s complete. %d errors.", job_id, len(jobs[job_id]["errors"]))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    leads = _parse_leads(data.get("leads", ""))
    if not leads:
        return jsonify({"error": "No leads provided"}), 400
    job_id = str(int(time.time() * 1000))
    threading.Thread(target=_run_job, args=(job_id, leads), daemon=True).start()
    return jsonify({"job_id": job_id, "total": len(leads)})


@app.route("/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/results")
def results():
    return jsonify(load_all_results())


@app.route("/clear", methods=["POST"])
def clear():
    clear_results()
    return jsonify({"ok": True})


@app.route("/errors/<job_id>")
def job_errors(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"errors": job.get("errors", [])})


if __name__ == "__main__":
    model_id = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    print("\n" + "=" * 60)
    print("Sales Intelligence Automator")
    print("Model : " + model_id)
    print("Server: http://127.0.0.1:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000)
