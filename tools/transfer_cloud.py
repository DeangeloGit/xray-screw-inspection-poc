"""Verify a connector download or use an independently authorized rclone remote."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import tempfile

import station_transfer as transfer
import transfer_crypto as crypto


def supplement_roundtrip(original, downloaded, keyfile, receipt=None):
    """Verify an evidence supplement independently of a full station package."""
    from kph33_supplement import restore
    original, downloaded = Path(original).resolve(), Path(downloaded).resolve()
    if transfer.sha(original) != transfer.sha(downloaded):
        raise ValueError('Drive 下載與本機原檔 SHA-256 不符')
    with tempfile.TemporaryDirectory(prefix='xray-kph33-cloud-restore-') as temp:
        restored = restore(downloaded, keyfile, Path(temp)/'isolated')
    result = dict(ok=True, cloud_verified=True, isolated_restore_verified=True,
                  supplement_only=True, sha256=transfer.sha(downloaded),
                  archive=original.name, files=restored['files'],
                  at=datetime.now(timezone.utc).isoformat())
    if receipt: transfer.write(receipt, result)
    return result


def roundtrip(original,downloaded,keyfile,receipt=None):
    original,downloaded=Path(original).resolve(),Path(downloaded).resolve()
    with original.open('rb') as f:
        if f.read(8) != crypto.MAGIC:raise ValueError('雲端移交只接受加密資料包')
    if transfer.sha(original)!=transfer.sha(downloaded):raise ValueError('Drive 下載與本機原檔 SHA-256 不符')
    with crypto.open_bundle(downloaded,keyfile) as plain:
        manifest=transfer.verify_archive(plain)
        if not manifest['complete']:raise ValueError('缺件備份不可通過完整移交驗收')
        with tempfile.TemporaryDirectory(prefix='xray-cloud-restore-') as temp:
            restored=transfer.import_bundle(plain,Path(temp)/'isolated')
            if not restored['validation']['ok']:raise ValueError('雲端下載後隔離匯入失敗')
    result=dict(ok=True,cloud_verified=True,isolated_restore_verified=True,sha256=transfer.sha(downloaded),
                at=datetime.now(timezone.utc).isoformat(),archive=original.name,files=len(manifest['files']),
                source_commit=manifest.get('source_commit'))
    if receipt:transfer.write(receipt,result)
    return result


def upload_rclone(archive,keyfile,remote,receipt=None):
    archive=Path(archive).resolve()
    if ':' not in remote:raise ValueError('請指定已自行 OAuth 授權的 rclone remote；不使用 Connector token')
    with archive.open('rb') as f:
        if f.read(8) != crypto.MAGIC:raise ValueError('拒絕上傳未加密檔案')
    with crypto.open_bundle(archive,keyfile) as plain:
        if not transfer.verify_archive(plain)['complete']:raise ValueError('拒絕上傳缺件包作為完整移交')
    target=remote.rstrip('/')+'/'+archive.name
    subprocess.run(['rclone','copyto',str(archive),target],check=True)
    subprocess.run(['rclone','copyto',str(archive)+'.sha256',target+'.sha256'],check=True)
    with tempfile.TemporaryDirectory(prefix='xray-drive-download-') as temp:
        downloaded=Path(temp)/archive.name
        subprocess.run(['rclone','copyto',target,str(downloaded)],check=True)
        subprocess.run(['rclone','copyto',target+'.sha256',str(downloaded)+'.sha256'],check=True)
        return roundtrip(archive,downloaded,keyfile,receipt)


def main():
    parser=argparse.ArgumentParser(description='Drive 下載回比及隔離還原驗收')
    parser.add_argument('archive');parser.add_argument('--key-file',required=True)
    parser.add_argument('--supplement',action='store_true',help='Verify KPH33 evidence supplement, not a complete station')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--downloaded');group.add_argument('--rclone-remote')
    parser.add_argument('--receipt')
    args=parser.parse_args()
    try:
        if args.supplement and not args.downloaded:raise ValueError('Supplement verification requires an actual downloaded file')
        if args.downloaded:result=(supplement_roundtrip if args.supplement else roundtrip)(args.archive,args.downloaded,args.key_file,args.receipt)
        else:result=upload_rclone(args.archive,args.key_file,args.rclone_remote,args.receipt)
        import json;print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,subprocess.CalledProcessError) as e:
        import json;print(json.dumps(dict(ok=False,error=str(e)),ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
