"""Download the supplied existing batch job. Never submits or purchases a job."""
import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('D:/Download/manifest.json'))
    parser.add_argument('--output', type=Path, default=Path('D:/Download/Databento'))
    parser.add_argument('--metadata-only', action='store_true', help='Test authentication on small JSON files only')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    job = manifest['job_id']
    if Path(job).name != job or '/' in job or '\\' in job:
        raise ValueError('Invalid job name')
    target = (args.output / job).resolve()
    target.mkdir(parents=True, exist_ok=True)
    files = manifest['files']
    if args.metadata_only:
        files = [f for f in files if f['filename'].endswith('.json')]
    # Read only a named environment variable, or ask locally with hidden input.
    key = os.environ.get('DATABENTO_API_KEY') or getpass.getpass('Databento API key (hidden, not saved): ')
    authorization = 'Basic ' + base64.b64encode((key.strip() + ':').encode()).decode()
    del key
    for number, entry in enumerate(files, 1):
        name = entry['filename']
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Unsafe filename')
        url = entry['urls']['https']
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'api.databento.com', 'hist.databento.com'}:
            raise ValueError('Unexpected download host')
        expected = entry['hash'].removeprefix('sha256:')
        dest = target / name
        if dest.exists() and dest.stat().st_size == entry['size'] and digest(dest) == expected:
            print(f'[{number}/{len(files)}] Verified, skip: {name}', flush=True)
            continue
        part = target / (name + '.part')
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'Authorization': authorization})
                # No redirect credential forwarding to an unrelated endpoint.
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        return None
                opener = urllib.request.build_opener(NoRedirect)
                print(f'[{number}/{len(files)}] Download {name}, attempt {attempt+1}', flush=True)
                with opener.open(request, timeout=60) as response, part.open('wb') as stream:
                    done = 0
                    checkpoint = time.monotonic()
                    for block in iter(lambda: response.read(4 * 1024 * 1024), b''):
                        stream.write(block)
                        done += len(block)
                        if time.monotonic() - checkpoint > 10:
                            print(f'  {done/1e6:.1f} / {entry["size"]/1e6:.1f} MB', flush=True)
                            checkpoint = time.monotonic()
                if part.stat().st_size != entry['size'] or digest(part) != expected:
                    raise ValueError('Size or SHA-256 mismatch')
                part.replace(dest)
                print('  SHA-256 verified', flush=True)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403}:
                    raise SystemExit(f'HTTP {exc.code}: verify API key and access to this job. No new job was submitted.')
                if 300 <= exc.code < 400:
                    raise SystemExit('Download redirected; verify the new endpoint before retrying.')
                if attempt == 2:
                    raise SystemExit(f'HTTP {exc.code}; rerun to skip verified files.')
                time.sleep(3)
            except (OSError, ValueError) as exc:
                if attempt == 2:
                    raise SystemExit(f'{type(exc).__name__}: download/checksum failed. Rerun to skip verified files.')
                time.sleep(3)
    print(f'Completed and verified {len(files)} files in {target}')


if __name__ == '__main__':
    main()
