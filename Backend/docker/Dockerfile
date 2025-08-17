FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    sudo \
    openssh-server \
    nano \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd

# Copy user creation script and user database CSV
COPY create_users.sh /create_users.sh
COPY students.csv /students.csv

RUN chmod +x /create_users.sh

# SSH config for demo/testing (adjust for production use)
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# Set TimeZone
RUN ln -sf /usr/share/zoneinfo/Australia/Sydney /etc/localtime

EXPOSE 22

# On container start: create users, set up assignment dirs, start SSH server
CMD ["/create_users.sh"]
