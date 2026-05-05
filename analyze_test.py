import json
from pathlib import Path

sessions_dir = Path('dataset_candidate/test/sessions')

for f in sorted(sessions_dir.glob('*.json')):
    s = json.load(open(f))
    tcodes = [e['tcode'] for e in s.get('transaction_log', [])]
    changes = s.get('change_log', [])
    os_cmds = s.get('os_command_log', [])
    system_log = s.get('system_log', [])

    print(f"{s['session_id']}")
    print(f"  reason:    {s['reason_code'][:70]}")
    print(f"  tcodes:    {', '.join(tcodes[:10])}")
    print(f"  changes:   {len(changes)} | os_cmds: {len(os_cmds)} | sys_log: {len(system_log)}")
    print(f"  requester: {s.get('ticket_requester', 'N/A')}")
    print()