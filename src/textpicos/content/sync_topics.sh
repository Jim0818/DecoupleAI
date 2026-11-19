#!/usr/bin/env bash
# The old append-to-catalog sync has retired. Planning reads selected files;
# candidate state belongs to the single candidate service.
printf '%s\n' 'TOPIC_SYNC_RETIRED: use python scripts/topics.py with a planning request, then candidate-upsert for an explicitly selected candidate.' >&2
exit 2
