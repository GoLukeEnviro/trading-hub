#!/bin/sh
set -e
GID=10000
for d in /freqtrade/user_data /freqtrade/user_data/logs; do
    if [ -d "$d" ]; then
        chgrp "$GID" "$d" || echo "WARN: chgrp $GID $d failed" >&2
        chmod 2775 "$d" || echo "WARN: chmod 2775 $d failed" >&2
    fi
done
for f in /freqtrade/user_data/*.json /freqtrade/user_data/*.log; do
    if [ -f "$f" ]; then
        chgrp "$GID" "$f" || echo "WARN: chgrp $GID $f failed" >&2
        chmod 664 "$f" || echo "WARN: chmod 664 $f failed" >&2
    fi
done
exec freqtrade "$@"
