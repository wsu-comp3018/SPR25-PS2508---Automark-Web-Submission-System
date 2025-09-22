FROM ubuntu:latest


ENV DEBIAN_FRONTEND=noninteractive TZ=Australia/Sydney
RUN apt-get update && apt-get install -y \
    openssh-server \
    subversion \
    nano \
    && rm -rf /var/lib/apt/lists/*

# openssh + tzdata for timezone; procps for `pgrep` (compose healthcheck); certs for good measure
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server tzdata procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# runtime dirs and the /home mount point your volume uses
RUN mkdir -p /var/run/sshd /home

# SSH config: enable password auth for students; disable root login; basic hardening
RUN sed -ri 's/^#?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -ri 's/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -ri 's/^#?UsePAM .*/UsePAM yes/' /etc/ssh/sshd_config && \
    sed -ri 's/^#?ChallengeResponseAuthentication .*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config && \
    printf '\n# User isolation configuration\nAllowTcpForwarding no\nX11Forwarding no\n' >> /etc/ssh/sshd_config

# Set timezone
RUN ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 22

# Foreground (-D) and log to stderr (-e) so `docker logs` shows sshd output
CMD ["/usr/sbin/sshd", "-D", "-e"]
