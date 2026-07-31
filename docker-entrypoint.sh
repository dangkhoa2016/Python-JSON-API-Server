#!/bin/sh
set -eu
python -m scripts.db_migrate
python -m scripts.db_seed_settings
case "${SEED_DATA_ON_STARTUP:-false}" in
    1|true|TRUE|yes|YES)
        python -m scripts.db_seed_startup
        ;;
    0|false|FALSE|no|NO|"")
        ;;
    *)
        echo "Invalid SEED_DATA_ON_STARTUP value: expected true/false" >&2
        exit 2
        ;;
esac
exec "$@"
