#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
workflow_file="$repo_dir/.github/workflows/sync-cloud-run-env.yml"

grep -Fq 'ENABLE_GITHUB_ENV_SYNC: ${{ vars.ENABLE_GITHUB_ENV_SYNC }}' "$workflow_file"
grep -Fq 'CLOUD_RUN_REGION: ${{ vars.CLOUD_RUN_REGION }}' "$workflow_file"
grep -Fq 'CLOUD_RUN_SERVICE: ${{ vars.CLOUD_RUN_SERVICE }}' "$workflow_file"
grep -Fq 'GOOGLE_CLOUD_PROJECT: ${{ vars.GOOGLE_CLOUD_PROJECT }}' "$workflow_file"
grep -Fq 'INCOME_THRESHOLD_USD: ${{ vars.INCOME_THRESHOLD_USD }}' "$workflow_file"
grep -Fq 'QQQI_INCOME_RATIO: ${{ vars.QQQI_INCOME_RATIO }}' "$workflow_file"
grep -Fq 'GLOBAL_TELEGRAM_CHAT_ID: ${{ vars.GLOBAL_TELEGRAM_CHAT_ID }}' "$workflow_file"
grep -Fq 'NOTIFY_LANG: ${{ vars.NOTIFY_LANG }}' "$workflow_file"
grep -Fq 'GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}' "$workflow_file"
grep -Fq 'TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}' "$workflow_file"
grep -Fq 'SCHWAB_API_KEY: ${{ secrets.SCHWAB_API_KEY }}' "$workflow_file"
grep -Fq 'SCHWAB_APP_SECRET: ${{ secrets.SCHWAB_APP_SECRET }}' "$workflow_file"
grep -Fq 'credentials_json: ${{ env.GCP_SA_KEY }}' "$workflow_file"
grep -Fq "Skipping Cloud Run env sync because ENABLE_GITHUB_ENV_SYNC is not set to true." "$workflow_file"
grep -Fq "Cloud Run env sync is enabled, but these values are missing:" "$workflow_file"
grep -Fq 'env_args+=("GOOGLE_CLOUD_PROJECT=${GOOGLE_CLOUD_PROJECT}")' "$workflow_file"
grep -Fq "if: steps.config.outputs.enabled == 'true'" "$workflow_file"
if grep -Fq -- "--remove-env-vars TELEGRAM_CHAT_ID" "$workflow_file"; then
  echo "workflow should not force-remove TELEGRAM_CHAT_ID; keep backward compatibility" >&2
  exit 1
fi
