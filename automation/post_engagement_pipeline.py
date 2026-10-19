import json
import os
import subprocess
import sys
import uuid

from datetime import datetime, timezone, timedelta
from pathlib import Path


# ======================================================
# PROJECT PATHS
# ======================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

LOG_DIR = (
    PROJECT_ROOT
    / "logs"
    / "automation"
)

LOCK_FILE = (
    PROJECT_ROOT
    / "data"
    / "network_scout_automation.lock"
)


# ======================================================
# PIPELINE SCRIPTS
# ======================================================

POST_MONITOR_SCRIPT = (
    PROJECT_ROOT
    / "browser"
    / "post_monitor.py"
)

POST_RANKING_SCRIPT = (
    PROJECT_ROOT
    / "ranking"
    / "post_relevance_ranker.py"
)


# ======================================================
# SETTINGS
# ======================================================

PIPELINE_NAME = (
    "post_engagement"
)

LOCK_STALE_AFTER = timedelta(
    hours=4
)


# ======================================================
# TIME
# ======================================================

def utc_now():
    return datetime.now(
        timezone.utc
    )


def utc_now_iso():
    return utc_now().isoformat()


def timestamp_for_filename():
    return utc_now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )


# ======================================================
# LOGGING
# ======================================================

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_FILE = (
    LOG_DIR
    / (
        f"{PIPELINE_NAME}_"
        f"{timestamp_for_filename()}.log"
    )
)


def log(message=""):
    text = str(message)

    print(
        text,
        flush=True,
    )

    with LOG_FILE.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            text + "\n"
        )


# ======================================================
# LOCK HELPERS
# ======================================================

def read_existing_lock():
    if not LOCK_FILE.exists():
        return None

    try:

        with LOCK_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception:
        return None

    return None


def is_lock_stale(
    lock_data,
):
    if not lock_data:
        return True

    created_at = (
        lock_data.get(
            "created_at"
        )
    )

    if not created_at:
        return True

    try:

        created_time = (
            datetime.fromisoformat(
                created_at
            )
        )

        if (
            created_time.tzinfo
            is None
        ):

            created_time = (
                created_time.replace(
                    tzinfo=timezone.utc
                )
            )

        age = (
            utc_now()
            - created_time
        )

        return (
            age
            > LOCK_STALE_AFTER
        )

    except Exception:

        return True


def acquire_lock():

    LOCK_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_lock = (
        read_existing_lock()
    )

    if LOCK_FILE.exists():

        if is_lock_stale(
            existing_lock
        ):

            try:

                LOCK_FILE.unlink()

            except Exception as error:

                raise RuntimeError(
                    "A stale automation lock exists "
                    "but could not be removed: "
                    f"{error}"
                )

        else:

            pipeline = (
                existing_lock.get(
                    "pipeline",
                    "unknown"
                )
                if existing_lock
                else "unknown"
            )

            created_at = (
                existing_lock.get(
                    "created_at",
                    "unknown"
                )
                if existing_lock
                else "unknown"
            )

            raise RuntimeError(
                "Another Network Scout automation "
                "is already running.\n"
                f"Pipeline: {pipeline}\n"
                f"Started: {created_at}"
            )

    lock_token = (
        str(
            uuid.uuid4()
        )
    )

    lock_data = {
        "token":
            lock_token,

        "pipeline":
            PIPELINE_NAME,

        "pid":
            os.getpid(),

        "created_at":
            utc_now_iso(),
    }

    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
    )

    try:

        file_descriptor = os.open(
            str(
                LOCK_FILE
            ),
            flags,
        )

        try:

            os.write(
                file_descriptor,
                json.dumps(
                    lock_data,
                    indent=4,
                ).encode(
                    "utf-8"
                ),
            )

        finally:

            os.close(
                file_descriptor
            )

    except FileExistsError:

        raise RuntimeError(
            "Another Network Scout automation "
            "started at the same time. "
            "This run has been stopped safely."
        )

    return lock_token


def release_lock(
    lock_token,
):
    if not LOCK_FILE.exists():
        return

    existing_lock = (
        read_existing_lock()
    )

    if not existing_lock:
        return

    if (
        existing_lock.get(
            "token"
        )
        != lock_token
    ):
        return

    try:

        LOCK_FILE.unlink()

    except Exception as error:

        log(
            "WARNING: Could not remove "
            f"automation lock: {error}"
        )


# ======================================================
# VALIDATION
# ======================================================

def validate_script(
    script_path,
):
    if script_path.exists():
        return

    raise FileNotFoundError(
        "Required pipeline script "
        f"does not exist:\n{script_path}"
    )


# ======================================================
# RUN STEP
# ======================================================

def run_step(
    step_number,
    step_name,
    script_path,
):
    validate_script(
        script_path
    )

    log()
    log(
        "=" * 70
    )

    log(
        f"STEP {step_number}: "
        f"{step_name}"
    )

    log(
        "=" * 70
    )

    log(
        f"Script: "
        f"{script_path.relative_to(PROJECT_ROOT)}"
    )

    log(
        f"Started: "
        f"{utc_now_iso()}"
    )

    command = [
        sys.executable,
        str(
            script_path
        ),
    ]

    process = subprocess.Popen(
        command,
        cwd=str(
            PROJECT_ROOT
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if process.stdout:

        for line in process.stdout:

            line = (
                line.rstrip()
            )

            log(
                line
            )

    return_code = (
        process.wait()
    )

    if return_code != 0:

        raise RuntimeError(
            f"{step_name} failed "
            f"with exit code "
            f"{return_code}."
        )

    log(
        f"Completed: "
        f"{utc_now_iso()}"
    )

    log(
        f"{step_name}: SUCCESS"
    )


# ======================================================
# POST PIPELINE
# ======================================================

def run_post_pipeline():

    log(
        "=" * 70
    )

    log(
        "NETWORK SCOUT — POST ENGAGEMENT PIPELINE"
    )

    log(
        "=" * 70
    )

    log(
        f"Project root: "
        f"{PROJECT_ROOT}"
    )

    log(
        f"Python: "
        f"{sys.executable}"
    )

    log(
        f"Started: "
        f"{utc_now_iso()}"
    )

    log(
        f"Log file: "
        f"{LOG_FILE}"
    )

    lock_token = None

    try:

        lock_token = (
            acquire_lock()
        )

        log()
        log(
            "Automation lock acquired."
        )

        # ----------------------------------------------
        # STEP 1
        # Check tracked people for new LinkedIn posts
        # ----------------------------------------------

        run_step(
            1,
            "Tracked Connection Post Monitor",
            POST_MONITOR_SCRIPT,
        )

        # ----------------------------------------------
        # STEP 2
        # Rank all pending post opportunities
        #
        # If there were no new posts, the ranker should
        # simply have nothing to process.
        # ----------------------------------------------

        run_step(
            2,
            "AI Post Relevance Ranking",
            POST_RANKING_SCRIPT,
        )

        log()
        log(
            "=" * 70
        )

        log(
            "POST ENGAGEMENT PIPELINE COMPLETE"
        )

        log(
            "=" * 70
        )

        log(
            "The Engagement Opportunities dashboard "
            "is now up to date."
        )

        log(
            f"Finished: "
            f"{utc_now_iso()}"
        )

        return 0

    except KeyboardInterrupt:

        log()
        log(
            "Pipeline stopped manually."
        )

        return 130

    except Exception as error:

        log()
        log(
            "=" * 70
        )

        log(
            "POST ENGAGEMENT PIPELINE FAILED"
        )

        log(
            "=" * 70
        )

        log(
            f"Error: {error}"
        )

        log(
            "Later steps were not run."
        )

        return 1

    finally:

        if lock_token:

            release_lock(
                lock_token
            )

            log(
                "Automation lock released."
            )


# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":

    exit_code = (
        run_post_pipeline()
    )

    sys.exit(
        exit_code
    )