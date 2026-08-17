#!/usr/bin/env bash
# Wrapper for cron: runs the job search agent from its own directory so
# relative paths (.env, jobs.db, jobs_digest.html) resolve correctly.
#
# Add to crontab with `crontab -e`, e.g. to run every morning at 8am:
#   0 8 * * * /path/to/job-search-agent/run_daily.sh >> /path/to/job-search-agent/cron.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
python3 main.py "$@"
