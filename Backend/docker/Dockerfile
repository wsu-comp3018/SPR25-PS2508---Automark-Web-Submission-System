FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive TZ=Australia/Sydney

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    nano \
    git \
    procps \
    netcat-openbsd \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd

COPY create_users.sh /create_users.sh
COPY students.csv /students.csv
RUN chmod +x /create_users.sh

# Dev-only SSH config tweaks (lock down for prod!)
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# Timezone already set via ENV
RUN ln -sf /usr/share/zoneinfo/$TZ /etc/localtime

EXPOSE 22

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD pgrep -x sshd >/dev/null || exit 1

CMD ["/create_users.sh"]
