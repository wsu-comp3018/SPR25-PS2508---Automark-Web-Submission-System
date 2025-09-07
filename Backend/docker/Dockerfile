FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /var/run/sshd

# SSH config for database-driven authentication
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Set TimeZone
RUN ln -sf /usr/share/zoneinfo/Australia/Sydney /etc/localtime

EXPOSE 22

# Start SSH daemon directly (users created via API)
CMD ["/usr/sbin/sshd", "-D"]
