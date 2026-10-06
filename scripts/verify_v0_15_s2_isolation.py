"""Read-only role/metadata proof. Never reads quantities or changes authentication."""

import argparse
import json
import subprocess
from pathlib import Path

from scripts.materialize_v0_15_s2_dataset import immutable

REMOTE = r"""
import hashlib,json,subprocess
def sql(statement,role):
 p=subprocess.run(['psql','-X','-h','127.0.0.1','-p','5433','-U',role,
 '-d','blueberry_history_v015','-At'],input=statement,capture_output=True,text=True)
 return p.stdout,p.stderr,p.returncode
statement=("BEGIN READ ONLY; SHOW transaction_read_only; "
"SELECT 1 FROM label_vault.harvest_records "
"WHERE season IN ('2023-2024','2024-2025','2025-2026') LIMIT 0; ROLLBACK;")
out,err,code=sql(statement,'blueberry_v015_predictor')
assert out.splitlines()==['BEGIN','on','ROLLBACK'] and 'permission denied' in err
metadata=("BEGIN READ ONLY; SHOW transaction_read_only; SELECT json_build_object("
"'label_schema',has_schema_privilege('blueberry_v015_predictor','label_vault','USAGE'),"
"'label_table',has_table_privilege('blueberry_v015_predictor',"
"'label_vault.harvest_records','SELECT'),'columns',"
"(SELECT json_agg(row_to_json(c) ORDER BY table_schema,table_name,ordinal_position) "
"FROM information_schema.columns c "
"WHERE table_schema IN ('authority','label_vault','predictor','audit'))); ROLLBACK;")
out,err,code=sql(metadata,'blueberry_v015_history')
lines=out.splitlines()
assert code==0 and lines[0:2]==['BEGIN','on'] and lines[-1]=='ROLLBACK'
meta=json.loads(lines[2]); assert not meta['label_schema'] and not meta['label_table']
print(json.dumps({'predictor_label_vault_denied':True,'read_only_enforced':True,'rollback':True,'source_schema_metadata_sha256':hashlib.sha256(json.dumps(meta,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'source_modified':False,'quantities_queried':False,'connection_authentication_changed':False,'os_identity_isolation_claimed':False,'existing_local_tcp_authentication_unchanged':True},sort_keys=True))
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ssh-profile", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    response = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", a.ssh_profile, "python3 -"],
        input=REMOTE,
        text=True,
        capture_output=True,
        check=True,
    )
    receipt = json.loads(response.stdout)
    immutable(a.output, receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
