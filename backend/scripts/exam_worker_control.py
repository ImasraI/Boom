"""Local terminal controls. Stop drains current requests; proxy reloads safely."""
import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.rag.exam_corpus import DEFAULT_ROOT
from app.rag.exam_control import set_proxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stop', 'proxy'))
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    if args.action == 'stop':
        DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
        (DEFAULT_ROOT/'stop-requested').touch()
        print('Stop requested. Current requests drain before exit; keep the terminal open.')
    else:
        if not args.value:
            parser.error('proxy requires http(s)://host:port, auto, or direct')
        try:
            set_proxy(DEFAULT_ROOT, args.value)
        except ValueError:
            parser.error('Invalid proxy. Use http(s)://host:port, auto, or direct; no credentials.')
        print('Proxy setting saved. Running workers reload after current requests drain.')


if __name__ == '__main__':
    main()
