#!/bin/bash

set -euo pipefail

IFS=,
while read userid password; do
    # Skip comments/blanks
    if [ -z "$userid" ] || [[ "$userid" == \#* ]]; then
        continue
    fi

    if ! id "$userid" &>/dev/null; then
        useradd -ms /bin/bash "$userid"
        echo "${userid}:${password}" | chpasswd
        # Build protected assignment dir structure
        mkdir -p "/home/${userid}/2025/AUT/PX/Assignment1" \
                 "/home/${userid}/2025/AUT/PX/Assignment2" \
                 "/home/${userid}/2025/SPR/PX/Assignment1" \
                 "/home/${userid}/2025/SPR/PX/Assignment2"
        # Set correct permissions
        chown root:root "/home/${userid}/2025" "/home/${userid}/2025/AUT" "/home/${userid}/2025/SPR" \
                        "/home/${userid}/2025/AUT/PX" "/home/${userid}/2025/SPR/PX"
        chmod 755 "/home/${userid}/2025" "/home/${userid}/2025/AUT" "/home/${userid}/2025/SPR" \
                  "/home/${userid}/2025/AUT/PX" "/home/${userid}/2025/SPR/PX"
        chown root:"${userid}" "/home/${userid}/2025/AUT/PX/Assignment1" "/home/${userid}/2025/AUT/PX/Assignment2" \
                               "/home/${userid}/2025/SPR/PX/Assignment1" "/home/${userid}/2025/SPR/PX/Assignment2"
        chmod 1770 "/home/${userid}/2025/AUT/PX/Assignment1" "/home/${userid}/2025/AUT/PX/Assignment2" \
                   "/home/${userid}/2025/SPR/PX/Assignment1" "/home/${userid}/2025/SPR/PX/Assignment2"

    fi
done < /students.csv

exec /usr/sbin/sshd -D
