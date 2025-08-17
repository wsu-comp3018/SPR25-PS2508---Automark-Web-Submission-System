FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    sudo \
    openssh-server \
    nano \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create SSH directory and set up SSH server
RUN mkdir /var/run/sshd

# Create a user 'student' with password 'student' and add to sudoers
RUN useradd -ms /bin/bash student && \
    echo "student:student" | chpasswd && \
    adduser student sudo

# Allow password authentication for SSH
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Set TimeZone
RUN ln -sf /usr/share/zoneinfo/Australia/Sydney /etc/localtime

# Expose SSH port
EXPOSE 22

# Start SSH server on container start
CMD ["/usr/sbin/sshd","-D"]
