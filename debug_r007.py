import json
from pathlib import Path

sessions_dir = Path('dataset_candidate/train/sessions')

false_positives = ['FF-TRAIN-0012', 'FF-TRAIN-0022', 'FF-TRAIN-0025', 'FF-TRAIN-0041']
false_negatives = ['FF-TRAIN-0002', 'FF-TRAIN-0014', 'FF-TRAIN-0049']

print('=== FALSE POSITIVES ===')
for sid in false_positives:
    s = json.load(open(sessions_dir / f'{sid}.json'))
    from datetime import datetime, timezone
    start = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00'))
    print(f'{sid} — hour: {start.hour} UTC')
    print(f'  reason: {s["reason_code"]}')
    print()

print('=== FALSE NEGATIVES ===')
for sid in false_negatives:
    s = json.load(open(sessions_dir / f'{sid}.json'))
    start = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00'))
    print(f'{sid} — hour: {start.hour} UTC')
    print(f'  reason: {s["reason_code"]}')
    print()

# add to debug_r007.py
print('=== CHECKING FALSE NEGATIVES HOUR ===')
for sid in ['FF-TRAIN-0002', 'FF-TRAIN-0014', 'FF-TRAIN-0049']:
    s = json.load(open(sessions_dir / f'{sid}.json'))
    from datetime import datetime
    start = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00'))
    hour = start.hour
    reason = s['reason_code'].lower()
    emergency_keywords = [
        "emergency", "critical", "urgent", "outage", "down", "failed",
        "failure", "incident", "production issue", "p1", "p2",
        "system down", "not working", "unavailable"
    ]
    matched = [kw for kw in emergency_keywords if kw in reason]
    print(f'{sid} hour={hour} outside={hour < 7 or hour >= 18} matched_keywords={matched}')